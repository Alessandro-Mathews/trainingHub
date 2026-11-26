CREATE TABLE plano (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    academia_id INTEGER NOT NULL,
    nome TEXT NOT NULL,
    descricao TEXT,
    valor_centavos INTEGER NOT NULL
        CHECK (typeof(valor_centavos) = 'integer' AND valor_centavos >= 0),
    duracao_dias INTEGER NOT NULL
        CHECK (typeof(duracao_dias) = 'integer' AND duracao_dias > 0),
    ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
    criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (academia_id, nome),
    FOREIGN KEY (academia_id) REFERENCES academia(id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT
);

CREATE INDEX idx_plano_academia_id ON plano(academia_id);
