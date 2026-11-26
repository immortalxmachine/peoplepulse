-- PeoplePulse star-schema DDL (PostgreSQL dialect).
-- AUTO-GENERATED from peoplepulse/warehouse/schema.py (SQLAlchemy Core),
-- which is the source of truth. Regenerate: python -m peoplepulse.warehouse.emit_sql
-- Local dev uses SQLite; CI runs this same model on PostgreSQL 16.

CREATE TABLE dim_department (
	department_key INTEGER NOT NULL, 
	department_name VARCHAR(48) NOT NULL, 
	function_group VARCHAR(32) NOT NULL, 
	PRIMARY KEY (department_key), 
	UNIQUE (department_name)
);

CREATE TABLE dim_job_role (
	job_role_key INTEGER NOT NULL, 
	job_role VARCHAR(48) NOT NULL, 
	department_name VARCHAR(48) NOT NULL, 
	PRIMARY KEY (job_role_key), 
	UNIQUE (job_role)
);

CREATE TABLE dim_education (
	education_key INTEGER NOT NULL, 
	education_level INTEGER NOT NULL, 
	education_label VARCHAR(24) NOT NULL, 
	PRIMARY KEY (education_key), 
	UNIQUE (education_level)
);

CREATE TABLE dim_employee (
	employee_key INTEGER NOT NULL, 
	employee_id VARCHAR(16) NOT NULL, 
	gender VARCHAR(6) NOT NULL, 
	age INTEGER NOT NULL, 
	marital_status VARCHAR(12) NOT NULL, 
	business_travel VARCHAR(20) NOT NULL, 
	overtime VARCHAR(3) NOT NULL, 
	department_key INTEGER NOT NULL, 
	job_role_key INTEGER NOT NULL, 
	education_key INTEGER NOT NULL, 
	education_field VARCHAR(24) NOT NULL, 
	job_level INTEGER NOT NULL, 
	attrition INTEGER NOT NULL, 
	PRIMARY KEY (employee_key), 
	UNIQUE (employee_id), 
	FOREIGN KEY(department_key) REFERENCES dim_department (department_key), 
	FOREIGN KEY(job_role_key) REFERENCES dim_job_role (job_role_key), 
	FOREIGN KEY(education_key) REFERENCES dim_education (education_key)
);

CREATE TABLE fact_employee (
	employee_key INTEGER NOT NULL, 
	department_key INTEGER NOT NULL, 
	job_role_key INTEGER NOT NULL, 
	monthly_income INTEGER NOT NULL, 
	daily_rate INTEGER NOT NULL, 
	hourly_rate INTEGER NOT NULL, 
	monthly_rate INTEGER NOT NULL, 
	distance_from_home INTEGER NOT NULL, 
	total_working_years INTEGER NOT NULL, 
	years_at_company INTEGER NOT NULL, 
	years_in_current_role INTEGER NOT NULL, 
	years_since_last_promotion INTEGER NOT NULL, 
	years_with_curr_manager INTEGER NOT NULL, 
	num_companies_worked INTEGER NOT NULL, 
	percent_salary_hike INTEGER NOT NULL, 
	training_times_last_year INTEGER NOT NULL, 
	job_satisfaction INTEGER NOT NULL, 
	environment_satisfaction INTEGER NOT NULL, 
	job_involvement INTEGER NOT NULL, 
	relationship_satisfaction INTEGER NOT NULL, 
	work_life_balance INTEGER NOT NULL, 
	performance_rating INTEGER NOT NULL, 
	stock_option_level INTEGER NOT NULL, 
	attrition INTEGER NOT NULL, 
	PRIMARY KEY (employee_key), 
	FOREIGN KEY(employee_key) REFERENCES dim_employee (employee_key), 
	FOREIGN KEY(department_key) REFERENCES dim_department (department_key), 
	FOREIGN KEY(job_role_key) REFERENCES dim_job_role (job_role_key)
);

CREATE TABLE quarantine (
	id INTEGER NOT NULL, 
	source_table VARCHAR(32) NOT NULL, 
	employee_id VARCHAR(16), 
	reason VARCHAR(48) NOT NULL, 
	raw_row VARCHAR(512) NOT NULL, 
	PRIMARY KEY (id)
);
