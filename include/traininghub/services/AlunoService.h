#pragma once

#include "traininghub/repositories/AlunoRepository.h"
#include "traininghub/repositories/InstrutorRepository.h"
#include "traininghub/security/ValidatedAuthContext.h"

namespace traininghub::services
{
enum class AlunoError
{
    InvalidInput, Unauthorized, Forbidden, UsuarioNotFound, IneligibleUsuario,
    NotFound, AlreadyExists, RelationshipConflict, Internal, InstrutorNotFound, IneligibleInstrutor
};

class AlunoService
{
public:
    using ErrorCallback = std::function<void(AlunoError)>;
    using FindCallback = std::function<void(const models::Aluno &)>;
    using ListCallback = repositories::AlunoRepository::ListCallback;
    using ResponsavelCallback = std::function<void(const std::optional<std::int64_t> &)>;

    AlunoService(repositories::AlunoRepository repository, repositories::InstrutorRepository instrutores);
    void criar(const security::ValidatedAuthContext &actor, std::int64_t usuarioId,
               FindCallback callback, ErrorCallback errorCallback) const;
    void buscarPorId(const security::ValidatedAuthContext &actor, std::int64_t id,
                     FindCallback callback, ErrorCallback errorCallback) const;
    void listarPorAcademia(const security::ValidatedAuthContext &actor, ListCallback callback,
                           ErrorCallback errorCallback) const;
    void buscarInstrutor(const security::ValidatedAuthContext &actor, std::int64_t alunoId,
                        ResponsavelCallback callback, ErrorCallback errorCallback) const;
    void definirInstrutor(const security::ValidatedAuthContext &actor, std::int64_t alunoId,
                         std::int64_t instrutorId, ResponsavelCallback callback,
                         ErrorCallback errorCallback) const;

private:
    repositories::AlunoRepository repository_;
    repositories::InstrutorRepository instrutores_;
};
}
