#pragma once

#include "traininghub/models/Matricula.h"

#include <drogon/orm/DbClient.h>
#include <functional>
#include <optional>
#include <vector>

namespace traininghub::repositories
{
struct ContextoCriacaoMatricula
{
    bool alunoExiste{};
    bool planoExiste{};
    bool usuarioAtivo{};
    bool perfilAtivo{};
    bool academiaAtiva{};
    bool planoAtivo{};
    bool vigenciaValida{};
    std::optional<std::string> perfilNome;
};

class MatriculaRepository
{
public:
    using FindCallback = std::function<void(const std::optional<models::Matricula> &)>;
    using ListCallback = std::function<void(const std::vector<models::Matricula> &)>;
    using AlunoListCallback = std::function<void(const std::optional<std::vector<models::Matricula>> &)>;
    using ContextCallback = std::function<void(const ContextoCriacaoMatricula &)>;
    using ErrorCallback = drogon::orm::ExceptionCallback;

    explicit MatriculaRepository(const drogon::orm::DbClientPtr &db);
    void verificarCriacao(std::int64_t academiaId, std::int64_t alunoId, std::int64_t planoId,
        ContextCallback callback, ErrorCallback errorCallback) const;
    void criar(std::int64_t academiaId, std::int64_t alunoId, std::int64_t planoId,
        const std::string &perfilNome, FindCallback callback, ErrorCallback errorCallback) const;
    void listarPorAcademia(std::int64_t academiaId, ListCallback callback, ErrorCallback errorCallback) const;
    void buscarPorId(std::int64_t academiaId, std::int64_t id, FindCallback callback, ErrorCallback errorCallback) const;
    void listarPorAluno(std::int64_t academiaId, std::int64_t alunoId,
        AlunoListCallback callback, ErrorCallback errorCallback) const;

private:
    drogon::orm::DbClientPtr db_;
};
}
