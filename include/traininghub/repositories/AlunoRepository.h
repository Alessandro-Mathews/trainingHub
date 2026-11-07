#pragma once

#include "traininghub/models/Aluno.h"

#include <drogon/orm/DbClient.h>
#include <functional>
#include <optional>
#include <vector>

namespace traininghub::repositories
{
struct UsuarioParaAluno
{
    bool usuarioAtivo{};
    bool academiaAtiva{};
    bool perfilAtivo{};
    std::optional<std::string> perfilNome;
    bool possuiAluno{};
};

class AlunoRepository
{
public:
    using FindCallback = std::function<void(const std::optional<models::Aluno> &)>;
    using ListCallback = std::function<void(const std::vector<models::Aluno> &)>;
    using UsuarioCallback = std::function<void(const std::optional<UsuarioParaAluno> &)>;
    using ErrorCallback = drogon::orm::ExceptionCallback;

    explicit AlunoRepository(const drogon::orm::DbClientPtr &db);
    void buscarUsuarioParaCriacao(std::int64_t academiaId, std::int64_t usuarioId,
                                 UsuarioCallback callback, ErrorCallback errorCallback) const;
    void criar(std::int64_t academiaId, std::int64_t usuarioId, const std::string &perfilNome,
               FindCallback callback, ErrorCallback errorCallback) const;
    void buscarPorId(std::int64_t academiaId, std::int64_t id,
                     FindCallback callback, ErrorCallback errorCallback) const;
    void listarPorAcademia(std::int64_t academiaId, ListCallback callback,
                           ErrorCallback errorCallback) const;

private:
    drogon::orm::DbClientPtr db_;
};
}
