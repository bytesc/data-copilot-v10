import re
from pathlib import Path

import pandas as pd
import requests

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


def get_ura_rental_func(project: str, ref_period: str = "26q3") -> pd.DataFrame:
    access_key = _get_access_key()
    token = _get_token(access_key)
    projects = _download_rental(access_key, token, ref_period)

    records = []
    for project_data in projects:
        project_name = project_data.get("project", "")
        if project.upper() not in project_name.upper():
            continue
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

    df = pd.DataFrame(records, columns=_KEYS)
    df["rent"] = pd.to_numeric(df["rent"], errors="coerce")
    if not df.empty:
        df = df.sort_values(by=["leaseDate", "rent"], ascending=[False, False])
    return df
