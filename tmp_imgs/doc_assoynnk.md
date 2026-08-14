# Simple Data Analysis: Entity Type Distribution in the Singapore Life Sciences Ecosystem

## Overview and Objective

The user requested a simple data analysis on a small portion of data, with the assistant selecting the dataset and analysis goal. The assistant chose to analyze the entity type distribution within the **Singapore Life Sciences Ecosystem** knowledge graph. The objective was to query the counts of different entity types from the `entity` table and visualize them using a bar chart, providing an overview of the ecosystem's composition. The analysis involved exploring the database schema, executing SQL to count entities grouped by `entity_type`, and plotting the top 10 entity types (out of 59 total) due to the high cardinality of categories.

## Database Schema Exploration

The analysis began with an exploration of the database schema to confirm that the `entity` table contains the `entity_type` column and to understand the table structure. The goal was to ensure the necessary data was available for analyzing entity type distribution.

### Schema Findings

The schema exploration (`explore_schema`) targeted the `entity` table and selected the `entity_type` field. The results revealed the following structure:

| Table   | Description                          | Rows   | Primary Key |
|---------|--------------------------------------|--------|-------------|
| `entity` | Entity master table · one row per graph node | 2,358 | `entity_id` |

The `entity_type` column was identified with these characteristics:

| Column        | Type                                              | Key | Comment                                                                                             |
|---------------|---------------------------------------------------|-----|-----------------------------------------------------------------------------------------------------|
| `entity_type` | VARCHAR(100) COLLATE "utf8mb4_unicode_ci"        |     | Subtype, e.g. Company – Biotech, Asset. Finer than stakeholder_role, coarser than entity_class      |

### Sample Data

Sample rows returned during schema exploration (showing only the `entity_type` column) confirmed the column contains subtype values:

| `entity_type` |
|---------------|
| Asset         |
| Asset         |
| Asset         |

### Table Availability Verification

To verify connectivity and that the table is queryable, a simple test query was executed:

```sql
SELECT * FROM entity LIMIT 1;
```

The query returned a row successfully, confirming that the `entity` table exists and contains data. The returned row included a populated `entity_type` value of `'Asset'`, demonstrating that the column is ready for aggregation.

### Conclusion

The schema exploration confirmed:

- The `entity` table is the master table with **2,358 rows**.
- The `entity_type` column exists as a **VARCHAR(100)** field with meaningful subtype values.
- The data is accessible via SQL queries, providing a solid foundation for subsequent grouping and visualization of entity type distribution.

## Query Execution and Error Handling

The initial attempt to query entity type counts failed with a data retrieval error:  
`'value' must be an instance of str or bytes, not a None`.  
To diagnose the issue, the assistant first verified the database connection and table availability by running a simple test query:

```sql
SELECT * FROM entity LIMIT 1;
```

This query returned a valid row, confirming that the `entity` table existed and was accessible.

With connectivity confirmed, the grouping query was executed successfully:

```sql
SELECT entity_type, COUNT(*) AS entity_count
FROM entity
GROUP BY entity_type
ORDER BY entity_count DESC;
```

The query returned **59 unique entity types**. The top 10 by count were:

| entity_type              | entity_count |
|--------------------------|--------------|
| Company – Biotech        | 574          |
| Asset                    | 460          |
| Asset – Clinical Trial   | 193          |
| Investor – VC / PE       | 189          |
| Academic – Research Institute | 152     |
| Company – Pharma         | 97           |
| None                     | 75           |
| Academic – University    | 74           |
| Company – Medical Device | 69           |
| Company – Diagnostics    | 44           |

Because the full list contained 59 categories, the analysis was limited to the top 10 for visualization purposes, though the complete dataset was available for further exploration.

## Data Visualization

To understand the distribution of entity types in the Singapore Life Sciences Ecosystem, a bar chart was generated. The assistant first queried the `entity` table to count the number of entities per `entity_type`. The query returned 59 distinct types, making a full chart impractical. Consequently, the assistant limited the visualization to the top 10 entity types by count, ensuring a clear and readable chart.

The following code snippet was used to fetch the data, filter to the top 10 if necessary, and plot the bar chart using `matplotlib` and `seaborn`:

```python
sql = "SELECT entity_type, COUNT(*) AS entity_count FROM entity GROUP BY entity_type ORDER BY entity_count DESC"
df = exe_sql(sql)

# Limit to top 10 types if more than 10 categories
if len(df) > 10:
    df = df.head(10)

plt.figure(figsize=(10, 6))
sns.set_style("whitegrid")
ax = sns.barplot(x='entity_type', y='entity_count', data=df, palette='viridis')
plt.xlabel('Entity Type')
plt.ylabel('Count')
plt.title('Distribution of Entity Types in Singapore Life Sciences Ecosystem')
plt.xticks(rotation=45, ha='right')
plt.tight_layout()
```

The resulting chart (saved as a PNG image) displays the top 10 entity types, with the most common being "Company – Biotech" (574 entities), followed by "Asset" (460), "Asset – Clinical Trial" (193), and others. The use of a whitegrid style, viridis color palette, rotated x-axis labels, and automatic layout adjustments ensures the chart is both informative and visually appealing.

## Summary and Completion

The simple data analysis of entity type distribution was completed successfully. The assistant queried the `entity` table, counted the number of entities per `entity_type`, and visualized the results in a bar chart. Because the query returned 59 distinct entity types, only the top 10 were displayed to keep the chart readable.

**Key findings:**
- **Company – Biotech** dominated with 574 entities, reflecting a strong biotech presence in the Singapore life sciences ecosystem.
- **Asset** (460) and **Asset – Clinical Trial** (193) followed, indicating a significant number of non‑company entities.
- The top 10 categories accounted for the majority of the dataset, with counts ranging from 44 to 574.

**Top 10 entity types:**

| Entity Type                 | Count |
|-----------------------------|-------|
| Company – Biotech           | 574   |
| Asset                       | 460   |
| Asset – Clinical Trial      | 193   |
| Investor – VC / PE          | 189   |
| Academic – Research Institute | 152 |
| Company – Pharma            | 97    |
| None                        | 75    |
| Academic – University       | 74    |
| Company – Medical Device    | 69    |
| Company – Diagnostics       | 44    |

The bar chart was generated using `seaborn` and `matplotlib`, saved to an image file, and presented to the user. The assistant concluded the task with a confirmation message: *“完成简单数据分析。我已从 entity 表中查询了实体类型分布，并绘制了柱状图。因为实体类型较多（59种），只显示了前10种。图表已保存。”*

