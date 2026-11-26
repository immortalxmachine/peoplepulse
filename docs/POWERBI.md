# Power BI — build the PeoplePulse MIS dashboard

The Streamlit app (`peoplepulse/dashboard/app.py`) is the live dashboard. This
guide reproduces the same MIS in **Power BI Desktop** over the exported star
schema, so the project also demonstrates the Power BI / DAX workflow the JD asks
for. All data is **SYNTHETIC**.

> You build the `.pbix` in Power BI Desktop (it is a binary file not committed
> here). Follow the steps below — they take ~15 minutes.

## 1. Export the data

```powershell
python -m peoplepulse.warehouse.export
```

This writes one CSV per table/view to `data_out/export/`. For Power BI you need
the dimension and fact tables:

```
dim_date.csv  dim_department.csv  dim_country.csv  dim_employee.csv
fact_headcount_monthly.csv  fact_exits.csv  fact_hiring_funnel.csv
```

## 2. Import into Power BI Desktop

1. **Home → Get data → Text/CSV** and load the seven files above.
2. In **Transform data (Power Query)**, confirm types: `date_key` = Whole
   Number, `full_date` = Date, measures = Whole Number / Decimal. Close & Apply.

## 3. Model the star schema (Model view)

Create these relationships (all **one-to-many**, single direction from the
dimension to the fact):

| From (1) | To (\*) |
|---|---|
| `dim_date[date_key]` | `fact_headcount_monthly[date_key]` |
| `dim_date[date_key]` | `fact_exits[date_key]` |
| `dim_date[date_key]` | `fact_hiring_funnel[date_key]` |
| `dim_department[department_key]` | each fact's `department_key` |
| `dim_country[country_key]` | each fact's `country_key` |
| `dim_employee[employee_key]` | `fact_exits[employee_key]` |

Mark **`dim_date`** as a date table (Table tools → Mark as date table →
`full_date`).

## 4. DAX measures

Create a measures table (Home → Enter data → empty table named `_Measures`) and
add:

```dax
-- Headcount (respects the current month/dept/country filter context)
Headcount = SUM ( fact_headcount_monthly[headcount] )

Current Headcount =
CALCULATE ( [Headcount], dim_date[date_key] = MAX ( dim_date[date_key] ) )

Exits = COUNTROWS ( fact_exits )

Voluntary Exits =
CALCULATE ( [Exits], fact_exits[exit_type] = "Voluntary" )

Involuntary Exits =
CALCULATE ( [Exits], fact_exits[exit_type] = "Involuntary" )

-- Average month-end headcount across the periods in context
Avg Headcount =
AVERAGEX ( VALUES ( dim_date[date_key] ), [Headcount] )

Monthly Attrition % =
DIVIDE ( [Exits], [Avg Headcount] )

-- Rolling 12-month (annualised) attrition
Rolling 12M Exits =
CALCULATE (
    [Exits],
    DATESINPERIOD ( dim_date[full_date], MAX ( dim_date[full_date] ), -12, MONTH )
)

Rolling 12M Avg Headcount =
AVERAGEX (
    DATESINPERIOD ( dim_date[full_date], MAX ( dim_date[full_date] ), -12, MONTH ),
    [Headcount]
)

Rolling 12M Attrition % =
DIVIDE ( [Rolling 12M Exits], [Rolling 12M Avg Headcount] )

-- Recruiting
Hires  = SUM ( fact_hiring_funnel[hires] )
Offers = SUM ( fact_hiring_funnel[offers] )
Accepts = SUM ( fact_hiring_funnel[accepts] )

Offer Acceptance % = DIVIDE ( [Accepts], [Offers] )

Avg Time To Hire =
DIVIDE (
    SUMX ( fact_hiring_funnel,
           fact_hiring_funnel[avg_time_to_hire_days] * fact_hiring_funnel[hires] ),
    [Hires]
)

-- Diversity
Female Headcount =
CALCULATE ( [Headcount], fact_headcount_monthly[gender] = "F" )

Female % = DIVIDE ( [Female Headcount], [Headcount] )
```

Format the `%` measures as Percentage, `Avg Time To Hire` as Decimal (1 dp).

## 5. Suggested report pages / visuals

| Visual | Fields |
|---|---|
| KPI cards | `Current Headcount`, `Rolling 12M Attrition %`, `Avg Time To Hire`, `Offer Acceptance %` |
| Line chart | Axis `dim_date[full_date]`, values `Headcount` |
| Line chart | Axis `full_date`, values `Monthly Attrition %` and `Rolling 12M Attrition %` |
| Clustered bar | Axis `dim_department[department_name]`, value `Avg Time To Hire`, legend `dim_country[country_name]` |
| Matrix | Rows `department_name`, columns `country_name`, value `Rolling 12M Attrition %` |
| Stacked column | Axis `dim_employee[grade]`, values `Female %` |
| Donut | Legend `fact_exits[exit_type]`, value `Exits` |
| Slicers | `dim_country[country_name]`, `dim_date[year]` |

The matrix + slicers reproduce the GenAI assistant's flagship question —
"attrition in UAE engineering" — as an interactive cross-tab.
