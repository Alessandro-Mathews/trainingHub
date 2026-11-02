-- Apply after 001_initial_schema.sql. Safe to repeat; existing records and IDs
-- are preserved, including inactive records requiring operator investigation.
INSERT INTO perfil (nome, descricao, ativo) VALUES
    ('Administrador', 'Administracao da propria academia', 1),
    ('Gestor', 'Gestao da propria academia', 1),
    ('Instrutor', 'Instrutor da academia', 1),
    ('Aluno', 'Aluno da academia', 1)
ON CONFLICT(nome) DO NOTHING;
