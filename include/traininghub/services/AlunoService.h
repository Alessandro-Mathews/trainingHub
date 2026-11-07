#pragma once

#include "traininghub/repositories/AlunoRepository.h"
#include "traininghub/security/ValidatedAuthContext.h"

namespace traininghub::services
{
enum class AlunoError
{
    InvalidInput, Unauthorized, Forbidden, UsuarioNotFound, IneligibleUsuario,
    NotFound, AlreadyExists, RelationshipConflict, Internal
};

class AlunoService
{
public:
    using ErrorCallback = std::function<void(AlunoError)>;
    using FindCallback = std::function<void(const models::Aluno &)>;
    using ListCallback = repositories::AlunoRepository::ListCallback;

    explicit AlunoService(repositories::AlunoRepository repository);
    void criar(const security::ValidatedAuthContext &actor, std::int64_t usuarioId,
               FindCallback callback, ErrorCallback errorCallback) const;
    void buscarPorId(const security::ValidatedAuthContext &actor, std::int64_t id,
                     FindCallback callback, ErrorCallback errorCallback) const;
    void listarPorAcademia(const security::ValidatedAuthContext &actor, ListCallback callback,
                           ErrorCallback errorCallback) const;

private:
    repositories::AlunoRepository repository_;
};
}
