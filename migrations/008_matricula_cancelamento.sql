ALTER TABLE matricula
ADD COLUMN cancelado_em DATETIME NULL
    CHECK (cancelado_em IS NULL OR (
        length(cancelado_em) = 19
        AND datetime(cancelado_em) IS NOT NULL
        AND datetime(cancelado_em) = cancelado_em
        AND cancelado_em >= data_inicio
        AND cancelado_em < data_fim
    ));
