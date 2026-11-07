#pragma once

#include "traininghub/repositories/InstrutorRepository.h"
#include "traininghub/security/ValidatedAuthContext.h"

namespace traininghub::services
{
enum class InstrutorError
{
    InvalidInput, Unauthorized, Forbidden, UsuarioNotFound, IneligibleUsuario,
    NotFound, AlreadyExists, RelationshipConflict, Internal
};

class InstrutorService
{
public:
    using ErrorCallback = std::function<void(InstrutorError)>;
    using FindCallback = std::function<void(const models::Instrutor &)>;
    using ListCallback = repositories::InstrutorRepository::ListCallback;

    explicit InstrutorService(repositories::InstrutorRepository repository);
    void criar(const security::ValidatedAuthContext &actor, std::int64_t usuarioId,
               FindCallback callback, ErrorCallback errorCallback) const;
    void buscarPorId(const security::ValidatedAuthContext &actor, std::int64_t id,
                     FindCallback callback, ErrorCallback errorCallback) const;
    void listarPorAcademia(const security::ValidatedAuthContext &actor, ListCallback callback,
                           ErrorCallback errorCallback) const;

private:
    repositories::InstrutorRepository repository_;
};
}
