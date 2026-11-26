# Power BI — build the PeoplePulse MIS dashboard

The Streamlit app (`peoplepulse/dashboard/app.py`) is the live dashboard. This
guide reproduces the same MIS in **Power BI Desktop** over the exported star
schema, so the project also demonstrates the Power BI / DAX workflow the JD asks
for.

Data is the **real** IBM HR Analytics Employee Attrition dataset (Kaggle,
DbCL-1.0) — a cross-sectional snapshot of 1,470 employees. There is one row per
employee with an `attrition` outcome (no dates), so the measures below are
cross-sectional cuts, not time series.

> You build the `.pbix` in Power BI Desktop (it is a binary file not committed
> here). Follow the steps below — they take ~15 minutes.

## 1. Export the data

```powershell
python -m peoplepulse.warehouse.export
```

This writes one CSV per table/view to `data_out/export/`. For Power BI you need
the dimension and fact tables:

```
dim_department.csv  dim_job_role.csv  dim_education.csv
dim_employee.csv    fact_employee.csv
```

## 2. Import into Power BI Desktop

1. **Home → Get data → Text/CSV** and load the five files above.
2. In **Transform data (Power Query)**, confirm types: keys = Whole Number,
   `monthly_income` / rates = Whole Number, `attrition` = Whole Number (1/0).
   Close & Apply.

## 3. Model the star schema (Model view)

Create these relationships (single direction from the dimension to the fact):

| From (1) | To (\*) |
|---|---|
| `dim_department[department_key]` | `dim_employee[department_key]` |
| `dim_job_role[job_role_key]` | `dim_employee[job_role_key]` |
| `dim_education[education_key]` | `dim_employee[education_key]` |
| `dim_employee[employee_key]` | `fact_employee[employee_key]` |

(`dim_employee` → `fact_employee` is one row to one row; model it as 1-to-1 or
1-to-many, cross-filter both directions.)

## 4. DAX measures

Create a measures table (Home → Enter data → empty table named `_Measures`) and
add:

```dax
Employees = COUNTROWS ( dim_employee )

Leavers = CALCULATE ( [Employees], dim_employee[attrition] = 1 )

Attrition % = DIVIDE ( [Leavers], [Employees] )

Avg Monthly Income = AVERAGE ( fact_employee[monthly_income] )

Avg Years At Company = AVERAGE ( fact_employee[years_at_company] )

-- Diversity
Female Employees =
CALCULATE ( [Employees], dim_employee[gender] = "Female" )

Female % = DIVIDE ( [Female Employees], [Employees] )

-- A known real driver: overtime raises attrition sharply
Attrition % (Overtime) =
CALCULATE ( [Attrition %], dim_employee[overtime] = "Yes" )
```

Format `Attrition %` and `Female %` as Percentage, income as Whole Number.

## 5. Suggested report pages / visuals

| Visual | Fields |
|---|---|
| KPI cards | `Employees`, `Attrition %`, `Avg Monthly Income` |
| Clustered bar | Axis `dim_department[department_name]`, value `Attrition %` |
| Clustered bar | Axis `dim_job_role[job_role]`, value `Attrition %` |
| Clustered bar | Axis `dim_employee[overtime]`, value `Attrition %` |
| Clustered bar | Axis `dim_employee[job_level]`, value `Attrition %` |
| Stacked column | Axis `dim_department[department_name]`, value `Female %` |
| Slicers | `dim_department[department_name]`, `dim_employee[overtime]`, `dim_employee[job_level]` |

The overtime slicer reproduces the assistant's flagship question — "attrition for
employees working overtime" — as an interactive cut.
