CREATE TABLE matricula (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    academia_id INTEGER NOT NULL,
    aluno_id INTEGER NOT NULL,
    plano_id INTEGER NOT NULL,
    nome_plano_contratado TEXT NOT NULL,
    valor_contratado_centavos INTEGER NOT NULL
        CHECK (typeof(valor_contratado_centavos) = 'integer' AND valor_contratado_centavos >= 0),
    duracao_contratada_dias INTEGER NOT NULL
        CHECK (typeof(duracao_contratada_dias) = 'integer' AND duracao_contratada_dias > 0),
    data_inicio DATETIME NOT NULL
        CHECK (length(data_inicio) = 19 AND datetime(data_inicio) IS NOT NULL
            AND datetime(data_inicio) = data_inicio),
    data_fim DATETIME NOT NULL
        CHECK (length(data_fim) = 19 AND datetime(data_fim) IS NOT NULL
            AND datetime(data_fim) = data_fim AND data_fim > data_inicio),
    criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (academia_id) REFERENCES academia(id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY (aluno_id) REFERENCES aluno(id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY (plano_id) REFERENCES plano(id)
        ON DELETE RESTRICT ON UPDATE RESTRICT
);

CREATE INDEX idx_matricula_academia_id ON matricula(academia_id);
CREATE INDEX idx_matricula_aluno_academia ON matricula(aluno_id, academia_id);
CREATE INDEX idx_matricula_plano_id ON matricula(plano_id);
