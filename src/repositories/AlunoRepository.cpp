#include "traininghub/repositories/AlunoRepository.h"

#include <utility>

namespace traininghub::repositories
{
namespace
{
models::Aluno fromRow(const drogon::orm::Row &row)
{
    return {row["id"].as<std::int64_t>(), row["usuario_id"].as<std::int64_t>(),
            row["criado_em"].as<std::string>()};
}

auto mapOne(AlunoRepository::FindCallback callback, AlunoRepository::ErrorCallback errorCallback)
{
    return [callback = std::move(callback), errorCallback](const drogon::orm::Result &result)
    {
        std::optional<models::Aluno> aluno;
        try
        {
            if (!result.empty()) aluno = fromRow(result[0]);
        }
        catch (...)
        {
            errorCallback(drogon::orm::ConversionError("Failed to map Aluno database result"));
            return;
        }
        callback(aluno);
    };
}

auto mapResponsavel(AlunoRepository::ResponsavelCallback callback,
                    AlunoRepository::ErrorCallback errorCallback)
{
    return [callback = std::move(callback), errorCallback](const drogon::orm::Result &result)
    {
        std::optional<InstrutorResponsavel> responsavel;
        try
        {
            if (!result.empty())
            {
                responsavel.emplace();
                if (!result[0]["instrutor_id"].isNull())
                    responsavel->instrutorId = result[0]["instrutor_id"].as<std::int64_t>();
                responsavel->consistente = result[0]["consistente"].as<int>() == 1;
            }
        }
        catch (...)
        {
            errorCallback(drogon::orm::ConversionError("Failed to map Aluno instructor relationship"));
            return;
        }
        callback(responsavel);
    };
}
}

AlunoRepository::AlunoRepository(const drogon::orm::DbClientPtr &db) : db_(db) {}

void AlunoRepository::buscarInstrutor(std::int64_t academiaId, std::int64_t alunoId,
    ResponsavelCallback callback, ErrorCallback errorCallback) const
{
    // Preserve administrative reads, but never expose an orphaned or foreign-tenant ID.
    db_->execSqlAsync(
        "SELECT al.instrutor_id, (al.instrutor_id IS NULL OR EXISTS ("
        "SELECT 1 FROM instrutor i JOIN usuario ui ON ui.id = i.usuario_id "
        "WHERE i.id = al.instrutor_id AND ui.academia_id = u.academia_id)) AS consistente "
        "FROM aluno al JOIN usuario u ON u.id = al.usuario_id "
        "WHERE u.academia_id = ? AND al.id = ?",
        mapResponsavel(std::move(callback), errorCallback), errorCallback, academiaId, alunoId);
}

void AlunoRepository::definirInstrutor(std::int64_t academiaId, std::int64_t alunoId,
    std::int64_t instrutorId, const std::string &perfilAluno, const std::string &perfilInstrutor,
    ResponsavelCallback callback, ErrorCallback errorCallback) const
{
    // Recheck both targets in the atomic write; earlier service reads can become stale.
    db_->execSqlAsync(
        "UPDATE aluno SET instrutor_id = ? WHERE id = ? AND EXISTS ("
        "SELECT 1 FROM usuario u JOIN perfil p ON p.id = u.perfil_id "
        "JOIN academia a ON a.id = u.academia_id "
        "WHERE u.id = aluno.usuario_id AND u.academia_id = ? "
        "AND u.ativo = 1 AND p.ativo = 1 AND p.nome = ? AND a.ativo = 1) "
        "AND EXISTS (SELECT 1 FROM instrutor i JOIN usuario u ON u.id = i.usuario_id "
        "JOIN perfil p ON p.id = u.perfil_id JOIN academia a ON a.id = u.academia_id "
        "WHERE i.id = ? AND u.academia_id = ? "
        "AND u.ativo = 1 AND p.ativo = 1 AND p.nome = ? AND a.ativo = 1) "
        "RETURNING instrutor_id, 1 AS consistente",
        mapResponsavel(std::move(callback), errorCallback), errorCallback,
        instrutorId, alunoId, academiaId, perfilAluno, instrutorId, academiaId, perfilInstrutor);
}

void AlunoRepository::buscarUsuarioParaCriacao(std::int64_t academiaId, std::int64_t usuarioId,
    UsuarioCallback callback, ErrorCallback errorCallback) const
{
    db_->execSqlAsync(
        "SELECT u.ativo AS usuario_ativo, a.ativo AS academia_ativa, "
        "p.ativo AS perfil_ativo, p.nome AS perfil_nome, al.id AS aluno_id "
        "FROM usuario u LEFT JOIN academia a ON a.id = u.academia_id "
        "LEFT JOIN perfil p ON p.id = u.perfil_id LEFT JOIN aluno al ON al.usuario_id = u.id "
        "WHERE u.academia_id = ? AND u.id = ?",
        [callback = std::move(callback), errorCallback](const drogon::orm::Result &result)
        {
            std::optional<UsuarioParaAluno> usuario;
            try
            {
                if (!result.empty())
                {
                    const auto &row = result[0];
                    usuario.emplace();
                    usuario->usuarioAtivo = row["usuario_ativo"].as<int>() == 1;
                    usuario->academiaAtiva = !row["academia_ativa"].isNull()
                        && row["academia_ativa"].as<int>() == 1;
                    usuario->perfilAtivo = !row["perfil_ativo"].isNull()
                        && row["perfil_ativo"].as<int>() == 1;
                    if (!row["perfil_nome"].isNull())
                        usuario->perfilNome = row["perfil_nome"].as<std::string>();
                    usuario->possuiAluno = !row["aluno_id"].isNull();
                }
            }
            catch (...)
            {
                errorCallback(drogon::orm::ConversionError("Failed to map Aluno eligibility"));
                return;
            }
            callback(usuario);
        }, errorCallback, academiaId, usuarioId);
}

void AlunoRepository::criar(std::int64_t academiaId, std::int64_t usuarioId,
    const std::string &perfilNome, FindCallback callback, ErrorCallback errorCallback) const
{
    // Recheck eligibility in the write statement; UNIQUE is the concurrent duplicate guard.
    // RETURNING avoids a second read and returns only the row inserted by this statement.
    db_->execSqlAsync(
        "INSERT INTO aluno (usuario_id) SELECT u.id FROM usuario u "
        "JOIN perfil p ON p.id = u.perfil_id JOIN academia a ON a.id = u.academia_id "
        "WHERE u.academia_id = ? AND u.id = ? AND u.ativo = 1 "
        "AND p.ativo = 1 AND p.nome = ? AND a.ativo = 1 "
        "RETURNING id, usuario_id, criado_em",
        mapOne(std::move(callback), errorCallback), errorCallback,
        academiaId, usuarioId, perfilNome);
}

void AlunoRepository::buscarPorId(std::int64_t academiaId, std::int64_t id,
    FindCallback callback, ErrorCallback errorCallback) const
{
    db_->execSqlAsync(
        "SELECT al.id, al.usuario_id, al.criado_em FROM aluno al "
        "JOIN usuario u ON u.id = al.usuario_id WHERE u.academia_id = ? AND al.id = ?",
        mapOne(std::move(callback), errorCallback), errorCallback, academiaId, id);
}

void AlunoRepository::listarPorAcademia(std::int64_t academiaId, ListCallback callback,
    ErrorCallback errorCallback) const
{
    db_->execSqlAsync(
        "SELECT al.id, al.usuario_id, al.criado_em FROM aluno al "
        "JOIN usuario u ON u.id = al.usuario_id WHERE u.academia_id = ? ORDER BY al.id",
        [callback = std::move(callback), errorCallback](const drogon::orm::Result &result)
        {
            std::vector<models::Aluno> alunos;
            try
            {
                alunos.reserve(result.size());
                for (const auto &row : result) alunos.push_back(fromRow(row));
            }
            catch (...)
            {
                errorCallback(drogon::orm::ConversionError("Failed to map Aluno database result"));
                return;
            }
            callback(alunos);
        }, errorCallback, academiaId);
}
}
