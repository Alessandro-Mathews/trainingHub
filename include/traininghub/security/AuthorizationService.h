#pragma once

#include "traininghub/repositories/AuthContextRepository.h"
#include "traininghub/security/ValidatedAuthContext.h"

namespace traininghub::security
{
enum class Operation { ContextRead, AcademiasRead, PerfisRead, PerfisManage, UsuariosRead, UsuariosCreate,
                       AlunosCreate, AlunosRead, InstrutoresCreate, InstrutoresRead,
                       AlunosInstrutorRead, AlunosInstrutorManage };
enum class AuthError { Unauthorized, Forbidden, Internal };

class AuthorizationService
{
public:
    using Callback = std::function<void(const ValidatedAuthContext &)>;
    using ErrorCallback = std::function<void(AuthError)>;
    explicit AuthorizationService(repositories::AuthContextRepository repository)
        : repository_(std::move(repository)) {}
    void validate(const AuthSession &session, Callback callback, ErrorCallback errorCallback) const;
    static bool allows(Role role, Operation operation);
    static bool canAssign(Role actor, Role target);
private:
    repositories::AuthContextRepository repository_;
};
}
