#include "traininghub/security/AuthorizationService.h"

namespace traininghub::security
{
void AuthorizationService::validate(const AuthSession &session, Callback callback,
                                    ErrorCallback errorCallback) const
{
    if (session.userId <= 0 || session.academiaId <= 0 || session.perfilId <= 0)
    {
        errorCallback(AuthError::Unauthorized);
        return;
    }
    repository_.find(session.userId,
        [session, callback, errorCallback](const std::optional<repositories::AuthRecord> &record)
        {
            if (!record || !record->userActive || !record->academiaActive
                || record->identity.academiaId != session.academiaId
                || record->identity.perfilId != session.perfilId)
            {
                errorCallback(AuthError::Unauthorized);
                return;
            }
            if (!record->perfilActive)
            {
                errorCallback(AuthError::Forbidden);
                return;
            }
            callback({record->identity, roleFromName(record->perfilName)});
        },
        [errorCallback](const drogon::orm::DrogonDbException &)
        {
            errorCallback(AuthError::Internal);
        });
}

bool AuthorizationService::allows(Role role, Operation operation)
{
    switch (operation)
    {
    case Operation::ContextRead:
        return role == Role::ADMIN || role == Role::GESTOR
            || role == Role::INSTRUTOR || role == Role::ALUNO;
    case Operation::AcademiasRead:
    case Operation::PerfisManage:
        return role == Role::ADMIN;
    case Operation::PerfisRead:
    case Operation::UsuariosRead:
    case Operation::UsuariosCreate:
    case Operation::AlunosCreate:
    case Operation::AlunosRead:
    case Operation::InstrutoresCreate:
    case Operation::InstrutoresRead:
    case Operation::AlunosInstrutorRead:
    case Operation::AlunosInstrutorManage:
    case Operation::UsuariosUpdate:
    case Operation::UsuariosManageStatus:
        return role == Role::ADMIN || role == Role::GESTOR;
    }
    return false;
}

bool AuthorizationService::canAssign(Role actor, Role target)
{
    if (actor != Role::ADMIN && actor != Role::GESTOR) return false;
    return target == Role::INSTRUTOR || target == Role::ALUNO
        || (actor == Role::ADMIN && target == Role::GESTOR);
}
}
