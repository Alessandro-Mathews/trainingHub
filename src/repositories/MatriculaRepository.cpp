#include "traininghub/repositories/MatriculaRepository.h"

#include <utility>
#include <chrono>

namespace traininghub::repositories
{
namespace
{
bool timestampCanonico(const std::string &text)
{
    if (text.size() != 19 || text[4] != '-' || text[7] != '-' || text[10] != ' '
        || text[13] != ':' || text[16] != ':') return false;
    for (std::size_t i = 0; i < text.size(); ++i)
        if (i != 4 && i != 7 && i != 10 && i != 13 && i != 16
            && (text[i] < '0' || text[i] > '9')) return false;
    const auto year = std::stoi(text.substr(0, 4));
    const auto month = static_cast<unsigned>(std::stoi(text.substr(5, 2)));
    const auto day = static_cast<unsigned>(std::stoi(text.substr(8, 2)));
    return std::chrono::year_month_day{std::chrono::year{year}, std::chrono::month{month},
        std::chrono::day{day}}.ok() && std::stoi(text.substr(11, 2)) < 24
        && std::stoi(text.substr(14, 2)) < 60 && std::stoi(text.substr(17, 2)) < 60;
}

models::Matricula fromRow(const drogon::orm::Row &row)
{
    models::Matricula value;
    value.id = row["id"].as<std::int64_t>();
    value.academiaId = row["academia_id"].as<std::int64_t>();
    value.alunoId = row["aluno_id"].as<std::int64_t>();
    value.planoId = row["plano_id"].as<std::int64_t>();
    value.nomePlanoContratado = row["nome_plano_contratado"].as<std::string>();
    value.valorContratadoCentavos = row["valor_contratado_centavos"].as<std::int64_t>();
    value.duracaoContratadaDias = row["duracao_contratada_dias"].as<std::int64_t>();
    value.dataInicio = row["data_inicio"].as<std::string>();
    value.dataFim = row["data_fim"].as<std::string>();
    value.criadoEm = row["criado_em"].as<std::string>();
    if (!row["cancelado_em"].isNull()) value.canceladoEm = row["cancelado_em"].as<std::string>();
    if (value.id <= 0 || value.academiaId <= 0 || value.alunoId <= 0 || value.planoId <= 0
        || value.valorContratadoCentavos < 0 || value.duracaoContratadaDias <= 0
        || value.dataInicio.size() != 19 || value.dataFim.size() != 19 || value.dataFim <= value.dataInicio)
        throw drogon::orm::ConversionError("Invalid Matricula persisted domain");
    if (value.canceladoEm && (!timestampCanonico(*value.canceladoEm)
        || *value.canceladoEm < value.dataInicio || *value.canceladoEm >= value.dataFim))
        throw drogon::orm::ConversionError("Invalid Matricula cancellation");
    return value;
}

MatriculaTemporal temporalFromRow(const drogon::orm::Row &row)
{
    auto value = MatriculaTemporal{fromRow(row), row["agora_utc"].as<std::string>()};
    if (!timestampCanonico(value.agoraUtc))
        throw drogon::orm::ConversionError("Invalid SQLite timestamp");
    return value;
}

auto mapOne(MatriculaRepository::FindCallback callback, MatriculaRepository::ErrorCallback errorCallback)
{
    return [callback = std::move(callback), errorCallback](const drogon::orm::Result &result)
    {
        std::optional<MatriculaTemporal> value;
        try
        {
            if (!result.empty()) value = temporalFromRow(result[0]);
        }
        catch (...)
        {
            errorCallback(drogon::orm::ConversionError("Failed to map Matricula database result"));
            return;
        }
        callback(value);
    };
}
}

MatriculaRepository::MatriculaRepository(const drogon::orm::DbClientPtr &db) : db_(db) {}

void MatriculaRepository::verificarCriacao(std::int64_t academiaId, std::int64_t alunoId,
    std::int64_t planoId, ContextCallback callback, ErrorCallback errorCallback) const
{
    // A single projection resolves both local targets before eligibility is considered.
    db_->execSqlAsync(
        "SELECT al.id AS aluno_id, al.ativo AS usuario_ativo, pf.ativo AS perfil_ativo, "
        "pf.nome AS perfil_nome, a.ativo AS academia_ativa, p.id AS plano_id, p.ativo AS plano_ativo, "
        "(datetime('now','+' || p.duracao_dias || ' days') IS NOT NULL "
        "AND datetime('now','+' || p.duracao_dias || ' days') > datetime('now')) AS vigencia_valida "
        "FROM (SELECT 1) seed LEFT JOIN (SELECT al.id,u.ativo,u.perfil_id,u.academia_id "
        "FROM aluno al JOIN usuario u ON u.id=al.usuario_id WHERE u.academia_id=?) al ON al.id=? "
        "LEFT JOIN perfil pf ON pf.id=al.perfil_id LEFT JOIN academia a ON a.id=al.academia_id "
        "LEFT JOIN plano p ON p.academia_id=? AND p.id=?",
        [callback = std::move(callback), errorCallback](const drogon::orm::Result &result)
        {
            ContextoCriacaoMatricula context;
            try
            {
                const auto &row = result[0];
                context.alunoExiste = !row["aluno_id"].isNull();
                context.planoExiste = !row["plano_id"].isNull();
                context.usuarioAtivo = !row["usuario_ativo"].isNull() && row["usuario_ativo"].as<int>() == 1;
                context.perfilAtivo = !row["perfil_ativo"].isNull() && row["perfil_ativo"].as<int>() == 1;
                context.academiaAtiva = !row["academia_ativa"].isNull() && row["academia_ativa"].as<int>() == 1;
                if (context.planoExiste)
                {
                    const auto active = row["plano_ativo"].as<int>();
                    if (active != 0 && active != 1)
                        throw drogon::orm::ConversionError("Invalid Plano activity");
                    context.planoAtivo = active == 1;
                }
                context.vigenciaValida = row["vigencia_valida"].as<int>() == 1;
                if (!row["perfil_nome"].isNull()) context.perfilNome = row["perfil_nome"].as<std::string>();
            }
            catch (...)
            {
                errorCallback(drogon::orm::ConversionError("Failed to map Matricula eligibility"));
                return;
            }
            callback(context);
        }, errorCallback, academiaId, alunoId, academiaId, planoId);
}

void MatriculaRepository::criar(std::int64_t academiaId, std::int64_t alunoId, std::int64_t planoId,
    const std::string &perfilNome, FindCallback callback, ErrorCallback errorCallback) const
{
    // Eligibility, commercial snapshot and UTC validity share the INSERT's effective state.
    db_->execSqlAsync(
        "INSERT INTO matricula (academia_id,aluno_id,plano_id,nome_plano_contratado,"
        "valor_contratado_centavos,duracao_contratada_dias,data_inicio,data_fim) "
        "SELECT u.academia_id,al.id,p.id,p.nome,p.valor_centavos,p.duracao_dias,datetime('now'),"
        "datetime('now','+' || p.duracao_dias || ' days') "
        "FROM aluno al JOIN usuario u ON u.id=al.usuario_id JOIN perfil pf ON pf.id=u.perfil_id "
        "JOIN academia a ON a.id=u.academia_id JOIN plano p ON p.id=? AND p.academia_id=u.academia_id "
        "WHERE al.id=? AND u.academia_id=? AND u.ativo=1 AND pf.ativo=1 AND pf.nome=? "
        "AND a.ativo=1 AND p.ativo=1 AND datetime('now','+' || p.duracao_dias || ' days') IS NOT NULL "
        "AND datetime('now','+' || p.duracao_dias || ' days') > datetime('now') "
        "RETURNING id,academia_id,aluno_id,plano_id,nome_plano_contratado,valor_contratado_centavos,"
        "duracao_contratada_dias,data_inicio,data_fim,criado_em,cancelado_em,data_inicio AS agora_utc",
        mapOne(std::move(callback), errorCallback), errorCallback, planoId, alunoId, academiaId, perfilNome);
}

void MatriculaRepository::listarPorAcademia(std::int64_t academiaId, ListCallback callback,
    ErrorCallback errorCallback) const
{
    db_->execSqlAsync(
        "WITH instante AS MATERIALIZED (SELECT datetime('now') AS agora_utc) "
        "SELECT m.id,m.academia_id,m.aluno_id,m.plano_id,m.nome_plano_contratado,"
        "m.valor_contratado_centavos,m.duracao_contratada_dias,m.data_inicio,m.data_fim,m.criado_em,"
        "m.cancelado_em,instante.agora_utc "
        "FROM matricula m JOIN aluno al ON al.id=m.aluno_id JOIN usuario u ON u.id=al.usuario_id "
        "JOIN plano p ON p.id=m.plano_id CROSS JOIN instante WHERE m.academia_id=? "
        "AND u.academia_id=m.academia_id AND p.academia_id=m.academia_id ORDER BY m.id",
        [callback = std::move(callback), errorCallback](const drogon::orm::Result &result)
        {
            std::vector<MatriculaTemporal> values;
            try
            {
                values.reserve(result.size());
                for (const auto &row : result) values.push_back(temporalFromRow(row));
            }
            catch (...)
            {
                errorCallback(drogon::orm::ConversionError("Failed to map Matricula database result"));
                return;
            }
            callback(values);
        }, errorCallback, academiaId);
}

void MatriculaRepository::buscarPorId(std::int64_t academiaId, std::int64_t id,
    FindCallback callback, ErrorCallback errorCallback) const
{
    db_->execSqlAsync(
        "WITH instante AS MATERIALIZED (SELECT datetime('now') AS agora_utc) "
        "SELECT m.id,m.academia_id,m.aluno_id,m.plano_id,m.nome_plano_contratado,"
        "m.valor_contratado_centavos,m.duracao_contratada_dias,m.data_inicio,m.data_fim,m.criado_em,"
        "m.cancelado_em,instante.agora_utc "
        "FROM matricula m JOIN aluno al ON al.id=m.aluno_id JOIN usuario u ON u.id=al.usuario_id "
        "JOIN plano p ON p.id=m.plano_id CROSS JOIN instante WHERE m.id=? AND m.academia_id=? "
        "AND u.academia_id=m.academia_id AND p.academia_id=m.academia_id",
        mapOne(std::move(callback), errorCallback), errorCallback, id, academiaId);
}

void MatriculaRepository::cancelar(std::int64_t academiaId, std::int64_t id,
    FindCallback callback, ErrorCallback errorCallback) const
{
    // Repeat the Service's transition condition at the effective write instant.
    db_->execSqlAsync(
        "UPDATE matricula SET cancelado_em=CURRENT_TIMESTAMP "
        "WHERE id=? AND academia_id=? AND cancelado_em IS NULL "
        "AND data_inicio<=CURRENT_TIMESTAMP AND CURRENT_TIMESTAMP<data_fim "
        "AND EXISTS (SELECT 1 FROM aluno al JOIN usuario u ON u.id=al.usuario_id "
        "JOIN plano p ON p.id=matricula.plano_id WHERE al.id=matricula.aluno_id "
        "AND u.academia_id=matricula.academia_id AND p.academia_id=matricula.academia_id) "
        "RETURNING id,academia_id,aluno_id,plano_id,nome_plano_contratado,valor_contratado_centavos,"
        "duracao_contratada_dias,data_inicio,data_fim,criado_em,cancelado_em,cancelado_em AS agora_utc",
        mapOne(std::move(callback), errorCallback), errorCallback, id, academiaId);
}

void MatriculaRepository::listarPorAluno(std::int64_t academiaId, std::int64_t alunoId,
    AlunoListCallback callback, ErrorCallback errorCallback) const
{
    // One snapshot distinguishes an unavailable parent from a local parent's empty history.
    db_->execSqlAsync(
        "WITH instante AS MATERIALIZED (SELECT datetime('now') AS agora_utc) "
        "SELECT m.id,m.academia_id,m.aluno_id,m.plano_id,m.nome_plano_contratado,"
        "m.valor_contratado_centavos,m.duracao_contratada_dias,m.data_inicio,m.data_fim,m.criado_em,"
        "m.cancelado_em,instante.agora_utc "
        "FROM aluno al JOIN usuario u ON u.id=al.usuario_id LEFT JOIN matricula m "
        "ON m.aluno_id=al.id AND m.academia_id=u.academia_id AND EXISTS "
        "(SELECT 1 FROM plano p WHERE p.id=m.plano_id AND p.academia_id=m.academia_id) "
        "CROSS JOIN instante WHERE al.id=? AND u.academia_id=? ORDER BY m.id",
        [callback = std::move(callback), errorCallback](const drogon::orm::Result &result)
        {
            std::optional<std::vector<MatriculaTemporal>> values;
            try
            {
                if (!result.empty())
                {
                    values.emplace();
                    for (const auto &row : result)
                        if (!row["id"].isNull()) values->push_back(temporalFromRow(row));
                }
            }
            catch (...)
            {
                errorCallback(drogon::orm::ConversionError("Failed to map Aluno enrollment history"));
                return;
            }
            callback(values);
        }, errorCallback, alunoId, academiaId);
}
}
