-- New databases receive this column from the SQLAlchemy model. When this
-- script is applied to an existing database, add it only when required.
SET @variant_assessments_exists = (
    SELECT COUNT(*)
    FROM information_schema.tables
    WHERE table_schema = DATABASE()
      AND table_name = 'variant_assessments'
);

SET @criterion_comments_exists = (
    SELECT COUNT(*)
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'variant_assessments'
      AND column_name = 'criterion_comments'
);

SET @criterion_comments_sql = IF(
    @variant_assessments_exists > 0 AND @criterion_comments_exists = 0,
    'ALTER TABLE variant_assessments ADD COLUMN criterion_comments TEXT NULL AFTER evidence_points',
    'SELECT 1'
);

PREPARE criterion_comments_statement FROM @criterion_comments_sql;
EXECUTE criterion_comments_statement;
DEALLOCATE PREPARE criterion_comments_statement;
