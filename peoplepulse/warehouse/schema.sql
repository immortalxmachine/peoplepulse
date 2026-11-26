-- PeoplePulse star-schema DDL (PostgreSQL dialect).
-- AUTO-GENERATED from peoplepulse/warehouse/schema.py (SQLAlchemy Core),
-- which is the source of truth. Regenerate: python -m peoplepulse.warehouse.emit_sql
-- Local dev uses SQLite; CI runs this same model on PostgreSQL 16.

CREATE TABLE dim_country (
	country_key INTEGER NOT NULL, 
	country_code VARCHAR(2) NOT NULL, 
	country_name VARCHAR(64) NOT NULL, 
	region VARCHAR(32) NOT NULL, 
	PRIMARY KEY (country_key), 
	UNIQUE (country_code)
);

CREATE TABLE dim_department (
	department_key INTEGER NOT NULL, 
	department_name VARCHAR(64) NOT NULL, 
	function_group VARCHAR(32) NOT NULL, 
	PRIMARY KEY (department_key), 
	UNIQUE (department_name)
);

CREATE TABLE dim_date (
	date_key INTEGER NOT NULL, 
	full_date DATE NOT NULL, 
	year INTEGER NOT NULL, 
	month INTEGER NOT NULL, 
	month_name VARCHAR(12) NOT NULL, 
	quarter VARCHAR(2) NOT NULL, 
	year_month VARCHAR(7) NOT NULL, 
	PRIMARY KEY (date_key)
);

CREATE TABLE dim_employee (
	employee_key INTEGER NOT NULL, 
	employee_id VARCHAR(16) NOT NULL, 
	full_name VARCHAR(80) NOT NULL, 
	gender VARCHAR(1) NOT NULL, 
	country_key INTEGER NOT NULL, 
	department_key INTEGER NOT NULL, 
	grade VARCHAR(4) NOT NULL, 
	band VARCHAR(4) NOT NULL, 
	annual_ctc_usd INTEGER NOT NULL, 
	hire_date DATE NOT NULL, 
	exit_date DATE, 
	exit_type VARCHAR(12), 
	exit_reason VARCHAR(32), 
	is_active INTEGER NOT NULL, 
	latest_rating INTEGER, 
	PRIMARY KEY (employee_key), 
	UNIQUE (employee_id), 
	FOREIGN KEY(country_key) REFERENCES dim_country (country_key), 
	FOREIGN KEY(department_key) REFERENCES dim_department (department_key)
);

CREATE TABLE fact_headcount_monthly (
	date_key INTEGER NOT NULL, 
	department_key INTEGER NOT NULL, 
	country_key INTEGER NOT NULL, 
	grade VARCHAR(4) NOT NULL, 
	gender VARCHAR(1) NOT NULL, 
	headcount INTEGER NOT NULL, 
	FOREIGN KEY(date_key) REFERENCES dim_date (date_key), 
	FOREIGN KEY(department_key) REFERENCES dim_department (department_key), 
	FOREIGN KEY(country_key) REFERENCES dim_country (country_key)
);

CREATE TABLE fact_exits (
	exit_key INTEGER NOT NULL, 
	date_key INTEGER NOT NULL, 
	employee_key INTEGER NOT NULL, 
	department_key INTEGER NOT NULL, 
	country_key INTEGER NOT NULL, 
	grade VARCHAR(4) NOT NULL, 
	gender VARCHAR(1) NOT NULL, 
	exit_type VARCHAR(12) NOT NULL, 
	exit_reason VARCHAR(32) NOT NULL, 
	tenure_days INTEGER NOT NULL, 
	PRIMARY KEY (exit_key), 
	FOREIGN KEY(date_key) REFERENCES dim_date (date_key), 
	FOREIGN KEY(employee_key) REFERENCES dim_employee (employee_key), 
	FOREIGN KEY(department_key) REFERENCES dim_department (department_key), 
	FOREIGN KEY(country_key) REFERENCES dim_country (country_key)
);

CREATE TABLE fact_hiring_funnel (
	funnel_key INTEGER NOT NULL, 
	date_key INTEGER NOT NULL, 
	department_key INTEGER NOT NULL, 
	country_key INTEGER NOT NULL, 
	applications INTEGER NOT NULL, 
	screened INTEGER NOT NULL, 
	interviewed INTEGER NOT NULL, 
	offers INTEGER NOT NULL, 
	accepts INTEGER NOT NULL, 
	hires INTEGER NOT NULL, 
	avg_time_to_hire_days FLOAT NOT NULL, 
	PRIMARY KEY (funnel_key), 
	FOREIGN KEY(date_key) REFERENCES dim_date (date_key), 
	FOREIGN KEY(department_key) REFERENCES dim_department (department_key), 
	FOREIGN KEY(country_key) REFERENCES dim_country (country_key)
);

CREATE TABLE quarantine (
	id INTEGER NOT NULL, 
	source_table VARCHAR(32) NOT NULL, 
	employee_id VARCHAR(16), 
	reason VARCHAR(48) NOT NULL, 
	raw_row VARCHAR(512) NOT NULL, 
	PRIMARY KEY (id)
);
