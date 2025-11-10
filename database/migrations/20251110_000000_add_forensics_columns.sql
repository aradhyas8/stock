-- Description: Add forensics accounting columns to fundamentals table
-- Up:

-- Add columns needed for Beneish M-Score
ALTER TABLE fundamentals ADD COLUMN receivables DECIMAL(15,2);
ALTER TABLE fundamentals ADD COLUMN ppe DECIMAL(15,2);  -- Property, Plant, Equipment
ALTER TABLE fundamentals ADD COLUMN depreciation DECIMAL(15,2);
ALTER TABLE fundamentals ADD COLUMN sga_expense DECIMAL(15,2);  -- Selling, General, Administrative

-- Add columns needed for Altman Z-Score
ALTER TABLE fundamentals ADD COLUMN cash DECIMAL(15,2);
ALTER TABLE fundamentals ADD COLUMN short_term_debt DECIMAL(15,2);
ALTER TABLE fundamentals ADD COLUMN retained_earnings DECIMAL(15,2);

-- Down:
-- Note: SQLite doesn't support DROP COLUMN, so rollback requires recreation
-- ALTER TABLE fundamentals DROP COLUMN receivables;
-- ALTER TABLE fundamentals DROP COLUMN ppe;
-- ALTER TABLE fundamentals DROP COLUMN depreciation;
-- ALTER TABLE fundamentals DROP COLUMN sga_expense;
-- ALTER TABLE fundamentals DROP COLUMN cash;
-- ALTER TABLE fundamentals DROP COLUMN short_term_debt;
-- ALTER TABLE fundamentals DROP COLUMN retained_earnings;
