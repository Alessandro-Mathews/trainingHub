#include "traininghub/repositories/PerfilRepository.h"

#include <drogon/drogon.h>

namespace traininghub::repositories
{

std::vector<models::Perfil> PerfilRepository::listar()
{
    std::vector<models::Perfil> perfis;

    auto dbClient = drogon::app().getDbClient();

    auto resultado = dbClient->execSqlSync(
        "SELECT id, nome, descricao, ativo, criado_em "
        "FROM perfil "
        "ORDER BY id"
    );

    for (const auto& linha : resultado)
    {
        models::Perfil perfil;

        perfil.id = linha["id"].as<std::int64_t>();
        perfil.nome = linha["nome"].as<std::string>();

        if (linha["descricao"].isNull())
        {
            perfil.descricao = std::nullopt;
        }
        else
        {
            perfil.descricao = linha["descricao"].as<std::string>();
        }

        perfil.ativo = linha["ativo"].as<int>();
        perfil.criado_em = linha["criado_em"].as<std::string>();

        perfis.push_back(perfil);
    }

    return perfis;
}


std::optional<models::Perfil>
PerfilRepository::buscarPorId(std::int64_t id)
{
    auto dbClient = drogon::app().getDbClient();

    auto resultado = dbClient->execSqlSync(
        "SELECT id, nome, descricao, ativo, criado_em "
        "FROM perfil "
        "WHERE id = ?",
        id
    );

    if (resultado.empty())
    {
        return std::nullopt;
    }

    const auto& linha = resultado.front();

    models::Perfil perfil;

    perfil.id = linha["id"].as<std::int64_t>();
    perfil.nome = linha["nome"].as<std::string>();

    if (linha["descricao"].isNull())
    {
        perfil.descricao = std::nullopt;
    }
    else
    {
        perfil.descricao = linha["descricao"].as<std::string>();
    }

    perfil.ativo = linha["ativo"].as<int>();
    perfil.criado_em = linha["criado_em"].as<std::string>();

    return perfil;
}


std::int64_t PerfilRepository::criar(
    const models::Perfil& perfil)
{
    auto dbClient = drogon::app().getDbClient();

    auto resultado = dbClient->execSqlSync(
        "INSERT INTO perfil "
        "(nome, descricao, ativo) "
        "VALUES (?, ?, ?)",
        perfil.nome,
        perfil.descricao.value_or(""),
        perfil.ativo
    );

    return resultado.insertId();
}


bool PerfilRepository::atualizar(
    std::int64_t id,
    const models::Perfil& perfil)
{
    auto dbClient = drogon::app().getDbClient();

    auto resultado = dbClient->execSqlSync(
        "UPDATE perfil "
        "SET nome = ?, descricao = ?, ativo = ? "
        "WHERE id = ?",
        perfil.nome,
        perfil.descricao.value_or(""),
        perfil.ativo,
        id
    );

    return resultado.affectedRows() > 0;
}


bool PerfilRepository::excluir(
    std::int64_t id)
{
    auto dbClient = drogon::app().getDbClient();

    auto resultado = dbClient->execSqlSync(
        "DELETE FROM perfil "
        "WHERE id = ?",
        id
    );

    return resultado.affectedRows() > 0;
}

}