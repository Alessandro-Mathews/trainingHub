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

struct InstrutorResponsavel
{
    std::optional<std::int64_t> instrutorId;
    bool consistente{true};
};

class AlunoRepository
{
public:
    using FindCallback = std::function<void(const std::optional<models::Aluno> &)>;
    using ListCallback = std::function<void(const std::vector<models::Aluno> &)>;
    using UsuarioCallback = std::function<void(const std::optional<UsuarioParaAluno> &)>;
    using ErrorCallback = drogon::orm::ExceptionCallback;
    using ResponsavelCallback = std::function<void(const std::optional<InstrutorResponsavel> &)>;

    explicit AlunoRepository(const drogon::orm::DbClientPtr &db);
    void buscarUsuarioParaCriacao(std::int64_t academiaId, std::int64_t usuarioId,
                                 UsuarioCallback callback, ErrorCallback errorCallback) const;
    void criar(std::int64_t academiaId, std::int64_t usuarioId, const std::string &perfilNome,
               FindCallback callback, ErrorCallback errorCallback) const;
    void buscarPorId(std::int64_t academiaId, std::int64_t id,
                     FindCallback callback, ErrorCallback errorCallback) const;
    void listarPorAcademia(std::int64_t academiaId, ListCallback callback,
                           ErrorCallback errorCallback) const;
    void buscarInstrutor(std::int64_t academiaId, std::int64_t alunoId,
                        ResponsavelCallback callback, ErrorCallback errorCallback) const;
    void definirInstrutor(std::int64_t academiaId, std::int64_t alunoId, std::int64_t instrutorId,
                         const std::string &perfilAluno, const std::string &perfilInstrutor,
                         ResponsavelCallback callback, ErrorCallback errorCallback) const;

private:
    drogon::orm::DbClientPtr db_;
};
}
