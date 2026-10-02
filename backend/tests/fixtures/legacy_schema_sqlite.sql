-- DDL of the single-user schema (before the users table), generated from the
-- models at commit 70bbc1e. Used by tests/test_migration.py to build an
-- 'existing' database. Do not edit.

CREATE TABLE assets (
	id INTEGER NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	category VARCHAR(60) NOT NULL, 
	interest_basis VARCHAR(10) NOT NULL, 
	profile VARCHAR(12) NOT NULL, 
	icon VARCHAR(8) NOT NULL, 
	units VARCHAR(10) NOT NULL, 
	wrapper VARCHAR(8) NOT NULL, 
	created_at DATETIME NOT NULL, 
	archived_at DATETIME, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_assets_category ON assets (category);

CREATE INDEX ix_assets_id ON assets (id);

CREATE INDEX ix_assets_profile ON assets (profile);

CREATE TABLE expenses (
	id INTEGER NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	amount NUMERIC(20, 2) NOT NULL, 
	currency VARCHAR(8) NOT NULL, 
	period VARCHAR(10) NOT NULL, 
	category VARCHAR(60) NOT NULL, 
	starts_on DATE NOT NULL, 
	ends_on DATE, 
	notes TEXT NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_expenses_ends_on ON expenses (ends_on);

CREATE INDEX ix_expenses_id ON expenses (id);

CREATE INDEX ix_expenses_starts_on ON expenses (starts_on);

CREATE TABLE income_sources (
	id INTEGER NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	kind VARCHAR(12) NOT NULL, 
	currency VARCHAR(8) NOT NULL, 
	params JSON NOT NULL, 
	starts_on DATE NOT NULL, 
	ends_on DATE, 
	notes TEXT NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_income_sources_ends_on ON income_sources (ends_on);

CREATE INDEX ix_income_sources_id ON income_sources (id);

CREATE INDEX ix_income_sources_starts_on ON income_sources (starts_on);

CREATE TABLE insights (
	id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	kind VARCHAR(16) NOT NULL, 
	period VARCHAR(7) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	language VARCHAR(2) NOT NULL, 
	content TEXT NOT NULL, 
	content_en TEXT NOT NULL, 
	data JSON NOT NULL, 
	data_localized JSON, 
	snapshot JSON NOT NULL, 
	ungrounded JSON NOT NULL, 
	model VARCHAR(64) NOT NULL, 
	translator VARCHAR(64) NOT NULL, 
	error TEXT NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_insights_created_at ON insights (created_at);

CREATE INDEX ix_insights_id ON insights (id);

CREATE INDEX ix_insights_kind ON insights (kind);

CREATE TABLE monthly_records (
	id INTEGER NOT NULL, 
	month VARCHAR(7) NOT NULL, 
	income NUMERIC(20, 2) NOT NULL, 
	actual_spent NUMERIC(20, 2) NOT NULL, 
	currency VARCHAR(8) NOT NULL, 
	notes TEXT NOT NULL, 
	commitments_paid TEXT, 
	other_spent NUMERIC(20, 2), 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_monthly_records_id ON monthly_records (id);

CREATE UNIQUE INDEX ix_monthly_records_month ON monthly_records (month);

CREATE TABLE reports (
	id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	style VARCHAR(16) NOT NULL, 
	language VARCHAR(2) NOT NULL, 
	content TEXT NOT NULL, 
	content_en TEXT NOT NULL, 
	model VARCHAR(64) NOT NULL, 
	translator VARCHAR(64) NOT NULL, 
	error TEXT NOT NULL, 
	snapshot JSON NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_reports_created_at ON reports (created_at);

CREATE INDEX ix_reports_id ON reports (id);

CREATE TABLE settings (
	"key" VARCHAR(60) NOT NULL, 
	value TEXT NOT NULL, 
	PRIMARY KEY ("key")
);

CREATE TABLE income_entries (
	id INTEGER NOT NULL, 
	source_id INTEGER NOT NULL, 
	month VARCHAR(7) NOT NULL, 
	amount NUMERIC(20, 2) NOT NULL, 
	units NUMERIC(10, 2), 
	costs NUMERIC(20, 2) NOT NULL, 
	override_net NUMERIC(20, 2), 
	notes TEXT NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_income_entry_source_month UNIQUE (source_id, month), 
	FOREIGN KEY(source_id) REFERENCES income_sources (id)
);

CREATE INDEX ix_income_entries_id ON income_entries (id);

CREATE INDEX ix_income_entries_month ON income_entries (month);

CREATE INDEX ix_income_entries_source_id ON income_entries (source_id);

CREATE TABLE positions (
	id INTEGER NOT NULL, 
	asset_id INTEGER NOT NULL, 
	amount NUMERIC(20, 6) NOT NULL, 
	currency VARCHAR(8) NOT NULL, 
	value_in_base NUMERIC(20, 4) NOT NULL, 
	price_used NUMERIC(20, 6) NOT NULL, 
	base_currency VARCHAR(8) NOT NULL, 
	notes TEXT NOT NULL, 
	accrues_from DATE, 
	flow_in_base NUMERIC(20, 4), 
	timestamp DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(asset_id) REFERENCES assets (id)
);

CREATE INDEX ix_positions_asset_id ON positions (asset_id);

CREATE INDEX ix_positions_id ON positions (id);

CREATE INDEX ix_positions_timestamp ON positions (timestamp);
