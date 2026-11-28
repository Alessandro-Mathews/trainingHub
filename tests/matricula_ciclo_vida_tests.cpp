#include "traininghub/services/MatriculaService.h"

#include <array>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <future>
#include <iostream>
#include <sstream>
#include <stdexcept>

namespace
{
void verificarEscritaCondicionada()
{
    using namespace traininghub;
    auto db = drogon::orm::DbClient::newSqlite3Client("filename=:memory:", 1);
    db->setTimeout(5.0);
    db->execSqlSync("PRAGMA foreign_keys=ON");
    db->execSqlSync("CREATE TABLE academia(id INTEGER PRIMARY KEY)");
    db->execSqlSync("CREATE TABLE usuario(id INTEGER PRIMARY KEY,academia_id INTEGER)");
    db->execSqlSync("CREATE TABLE aluno(id INTEGER PRIMARY KEY,usuario_id INTEGER)");
    db->execSqlSync("CREATE TABLE plano(id INTEGER PRIMARY KEY,academia_id INTEGER)");
    const auto root = std::filesystem::path{__FILE__}.parent_path().parent_path();
    for (const auto *name : {"007_matricula.sql", "008_matricula_cancelamento.sql"})
    {
        std::ifstream file(root / "migrations" / name);
        if (!file) throw std::runtime_error("Cannot read Matricula migration");
        std::stringstream script;
        script << file.rdbuf();
        std::string statement;
        while (std::getline(script, statement, ';'))
            if (statement.find_first_not_of(" \r\n\t") != std::string::npos) db->execSqlSync(statement);
    }
    db->execSqlSync("INSERT INTO academia VALUES(1)");
    db->execSqlSync("INSERT INTO usuario VALUES(1,1)");
    db->execSqlSync("INSERT INTO aluno VALUES(1,1)");
    db->execSqlSync("INSERT INTO plano VALUES(1,1)");
    db->execSqlSync("INSERT INTO matricula(academia_id,aluno_id,plano_id,nome_plano_contratado,"
        "valor_contratado_centavos,duracao_contratada_dias,data_inicio,data_fim) "
        "VALUES(1,1,1,'Teste',0,2,datetime('now','-1 day'),datetime('now','+1 day'))");
    repositories::MatriculaRepository repository{db};
    const auto awaitRecord = [](auto operation)
    {
        using Record = std::optional<repositories::MatriculaTemporal>;
        auto promise = std::make_shared<std::promise<Record>>();
        auto future = promise->get_future();
        operation([promise](const Record &value) { promise->set_value(value); },
            [promise](const drogon::orm::DrogonDbException &)
            { promise->set_exception(std::make_exception_ptr(std::runtime_error("Repository failed"))); });
        if (future.wait_for(std::chrono::seconds{5}) != std::future_status::ready)
            throw std::runtime_error("Repository callback timed out");
        return future.get();
    };
    const auto previous = awaitRecord([&](auto success, auto error)
        { repository.buscarPorId(1, 1, success, error); });
    if (!previous || services::MatriculaService::determinarSituacao(previous->matricula, previous->agoraUtc)
        != services::SituacaoMatricula::Ativa) throw std::runtime_error("Fixture must initially be active");
    // Simulate expiry after pre-reading, without sleeping or a production synchronization hook.
    db->execSqlSync("UPDATE matricula SET data_inicio='2000-01-01 00:00:00',data_fim='2000-01-03 00:00:00'");
    const auto expired = awaitRecord([&](auto success, auto error) { repository.cancelar(1, 1, success, error); });
    if (expired || !db->execSqlSync("SELECT cancelado_em FROM matricula")[0][0].isNull())
        throw std::runtime_error("Effective write must reject expired validity");
    db->execSqlSync("UPDATE matricula SET data_inicio=datetime('now','-1 day'),data_fim=datetime('now','+1 day')");
    const auto external = awaitRecord([&](auto success, auto error) { repository.cancelar(2, 1, success, error); });
    if (external) throw std::runtime_error("Repository write must restrict tenant");
    const auto cancelled = awaitRecord([&](auto success, auto error) { repository.cancelar(1, 1, success, error); });
    const auto repeated = awaitRecord([&](auto success, auto error) { repository.cancelar(1, 1, success, error); });
    if (!cancelled || !cancelled->matricula.canceladoEm || repeated
        || db->execSqlSync("SELECT cancelado_em FROM matricula")[0][0].as<std::string>() != *cancelled->matricula.canceladoEm)
        throw std::runtime_error("Conditional write must preserve first cancellation");
    db->closeAll();
}
}

int main()
{
    using namespace traininghub::services;
    try
    {
        traininghub::models::Matricula matricula;
        matricula.dataInicio = "2026-01-01 00:00:00";
        matricula.dataFim = "2026-02-01 00:00:00";
        const std::array cases{
            std::pair{"2025-12-31 23:59:59", SituacaoMatricula::Inativa},
            std::pair{"2026-01-01 00:00:00", SituacaoMatricula::Ativa},
            std::pair{"2026-01-15 12:00:00", SituacaoMatricula::Ativa},
            std::pair{"2026-02-01 00:00:00", SituacaoMatricula::Inativa},
            std::pair{"2026-02-01 00:00:01", SituacaoMatricula::Inativa}
        };
        for (const auto &[instant, expected] : cases)
            if (MatriculaService::determinarSituacao(matricula, instant) != expected)
                throw std::runtime_error("Incorrect validity boundary");
        matricula.canceladoEm = "2026-01-15 12:00:00";
        if (MatriculaService::determinarSituacao(matricula, "2026-01-15 12:00:00") != SituacaoMatricula::Cancelada)
            throw std::runtime_error("Cancellation must override active validity");
        if (MatriculaService::determinarSituacao(matricula, "2026-02-02 00:00:00") != SituacaoMatricula::Cancelada)
            throw std::runtime_error("Cancellation must survive natural expiration");
        matricula.canceladoEm = matricula.dataInicio;
        if (MatriculaService::determinarSituacao(matricula, matricula.dataInicio) != SituacaoMatricula::Cancelada)
            throw std::runtime_error("Cancellation at inclusive start must be preserved");
        std::cout << "Matricula lifecycle: 8 deterministic Service cases passed.\n";
        verificarEscritaCondicionada();
        std::cout << "Repository gates: expiry after pre-read, tenant and immutable cancellation passed.\n";
        return 0;
    }
    catch (const std::exception &error)
    {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
