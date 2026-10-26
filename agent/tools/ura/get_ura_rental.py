import re
from pathlib import Path

import pandas as pd
import requests
from sqlalchemy import text
from sqlalchemy.types import VARCHAR, Float

from data_access.db_conn import engine

URA_ACCESS_KEY_PATH = Path(__file__).resolve().parent / "ura_access_key.txt"

TOKEN_URL = "https://eservice.ura.gov.sg/uraDataService/insertNewToken/v1"
RENTAL_URL = "https://eservice.ura.gov.sg/uraDataService/invokeUraDS/v1"
SERVICE = "PMI_Resi_Rental"

_KEYS = [
    "project",
    "street",
    "leaseDate",
    "propertyType",
    "noOfBedRoom",
    "areaSqft",
    "rent",
    "district",
]

RENTAL_TABLE_NAME = "ura_resi_rental"

_RENTAL_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS `ura_resi_rental` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `project` VARCHAR(255) NULL COMMENT 'Condo project name',
  `street` VARCHAR(255) NULL COMMENT 'Street name',
  `lease_date` VARCHAR(50) NULL COMMENT 'Lease commencement date (YYYY-MM-DD)',
  `property_type` VARCHAR(100) NULL COMMENT 'Property type, e.g. Condominium',
  `no_of_bedroom` VARCHAR(50) NULL COMMENT 'Number of bedrooms',
  `area_sqft` VARCHAR(50) NULL COMMENT 'Floor area in square feet',
  `rent` FLOAT NULL COMMENT 'Monthly rent in SGD',
  `district` VARCHAR(50) NULL COMMENT 'District number',
  `ref_period` VARCHAR(20) NULL COMMENT 'URA reference period, e.g. 26q3',
  PRIMARY KEY (`id`),
  INDEX `idx_ref_period` (`ref_period`),
  INDEX `idx_project` (`project`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='URA residential rental contracts downloaded from the URA data service.'
"""

_RENTAL_COLUMN_TYPES = {
    "project": VARCHAR(255),
    "street": VARCHAR(255),
    "lease_date": VARCHAR(50),
    "property_type": VARCHAR(100),
    "no_of_bedroom": VARCHAR(50),
    "area_sqft": VARCHAR(50),
    "rent": Float(),
    "district": VARCHAR(50),
    "ref_period": VARCHAR(20),
}

_RENTAL_COLUMN_RENAME = {
    "leaseDate": "lease_date",
    "propertyType": "property_type",
    "noOfBedRoom": "no_of_bedroom",
    "areaSqft": "area_sqft",
}


def _get_access_key() -> str:
    if not URA_ACCESS_KEY_PATH.exists():
        raise RuntimeError(
            f"URA access key file not found: {URA_ACCESS_KEY_PATH}"
        )
    return URA_ACCESS_KEY_PATH.read_text(encoding="utf-8").strip()


def _get_token(access_key: str) -> str:
    r = requests.get(
        TOKEN_URL,
        headers={
            "AccessKey": access_key,
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
        timeout=30,
    )
    r.raise_for_status()
    if "application/json" not in r.headers.get("Content-Type", "").lower():
        raise RuntimeError(
            f"URA returned non-JSON token response: "
            f"HTTP {r.status_code}, Content-Type={r.headers.get('Content-Type')}"
        )
    response = r.json()
    if response.get("Status") != "Success":
        raise RuntimeError(f"URA token error: {response}")
    return response["Result"]


def _download_rental(access_key: str, token: str, ref_period: str) -> list:
    r = requests.get(
        RENTAL_URL,
        params={"service": SERVICE, "refPeriod": ref_period},
        headers={
            "AccessKey": access_key,
            "Token": token,
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
        timeout=60,
    )
    r.raise_for_status()
    if "application/json" not in r.headers.get("Content-Type", "").lower():
        raise RuntimeError(
            f"URA returned non-JSON rental response: "
            f"HTTP {r.status_code}, Content-Type={r.headers.get('Content-Type')}"
        )
    data = r.json()
    if data.get("Status") != "Success":
        raise RuntimeError(f"URA rental API error: {data}")
    return data.get("Result", [])


def _flatten_rental_records(projects: list) -> list:
    records = []
    for project_data in projects:
        project_name = project_data.get("project", "")
        for rental in project_data.get("rental", []):
            records.append({
                "project": project_name,
                "street": project_data.get("street", ""),
                "leaseDate": rental.get("leaseDate"),
                "propertyType": rental.get("propertyType"),
                "noOfBedRoom": rental.get("noOfBedRoom"),
                "areaSqft": rental.get("areaSqft"),
                "rent": rental.get("rent"),
                "district": rental.get("district"),
            })
    return records


def import_rental_to_db(records: list, ref_period: str) -> int:
    df = pd.DataFrame(records, columns=_KEYS)
    if df.empty:
        return 0
    df["rent"] = pd.to_numeric(df["rent"], errors="coerce")
    df = df.rename(columns=_RENTAL_COLUMN_RENAME)
    df["ref_period"] = ref_period
    with engine.begin() as conn:
        conn.execute(text(_RENTAL_TABLE_SQL))
        conn.execute(
            text(f"DELETE FROM `{RENTAL_TABLE_NAME}` WHERE `ref_period` = :rp"),
            {"rp": ref_period},
        )
    df.to_sql(
        name=RENTAL_TABLE_NAME,
        con=engine,
        if_exists="append",
        index=False,
        dtype=_RENTAL_COLUMN_TYPES,
    )
    return len(df)


def get_ura_rental_func(project: str, ref_period: str = "26q3") -> pd.DataFrame:
    access_key = _get_access_key()
    token = _get_token(access_key)
    projects = _download_rental(access_key, token, ref_period)

    all_records = _flatten_rental_records(projects)
    imported = import_rental_to_db(all_records, ref_period)
    print(
        f"Imported {imported} URA rental records for ref period {ref_period} "
        f"into table '{RENTAL_TABLE_NAME}' in the singapore_land_2 database."
    )

    df = pd.DataFrame(all_records, columns=_KEYS)
    df["rent"] = pd.to_numeric(df["rent"], errors="coerce")
    if not df.empty:
        df = df[df["project"].str.upper().str.contains(project.upper())]
        df = df.sort_values(by=["leaseDate", "rent"], ascending=[False, False])
    return df
