CREATE TABLE IF NOT EXISTS query_run (
    id VARCHAR(36) PRIMARY KEY,
    request_key VARCHAR(80) NOT NULL UNIQUE,
    question VARCHAR(400) NOT NULL,
    status VARCHAR(20) NOT NULL,
    started BOOLEAN NOT NULL DEFAULT FALSE,
    result_json TEXT,
    message VARCHAR(600)
);

CREATE TABLE IF NOT EXISTS demo_order (
    id INT PRIMARY KEY,
    period_month CHAR(7) NOT NULL,
    region VARCHAR(12) NOT NULL,
    order_status VARCHAR(12) NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    refund DECIMAL(12,2) NOT NULL
);
