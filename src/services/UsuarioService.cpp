#include "traininghub/services/UsuarioService.h"
#include "traininghub/security/PasswordHasher.h"

#include <utility>

namespace traininghub::services
{
namespace
{
bool validEmail(const std::string &email)
{
    const auto at = email.find('@');
    return at != std::string::npos && at > 0 && at + 1 < email.size()
        && email.find('@', at + 1) == std::string::npos
        && email.find_first_of(" \t\r\n\f\v") == std::string::npos
        && email.find('\0') == std::string::npos;
}

repositories::UsuarioRepository::ErrorCallback databaseError(UsuarioService::ErrorCallback callback)
{
    return [callback = std::move(callback)](const drogon::orm::DrogonDbException &error)
    {
        if (dynamic_cast<const drogon::orm::UniqueViolation *>(&error))
            callback(UsuarioError::DuplicateEmail);
        else if (dynamic_cast<const drogon::orm::ForeignKeyViolation *>(&error))
            callback(UsuarioError::RelationshipConflict);
        else
            callback(UsuarioError::Internal);
    };
}
}

UsuarioService::UsuarioService(repositories::UsuarioRepository usuarios,
                               repositories::AcademiaRepository academias,
                               repositories::PerfilRepository perfis)
    : usuarios_(std::move(usuarios)), academias_(std::move(academias)), perfis_(std::move(perfis))
{
}

void UsuarioService::criar(const NovoUsuario &input, FindCallback callback,
                           ErrorCallback errorCallback) const
{
    if (input.academia_id <= 0 || input.perfil_id <= 0
        || input.nome.find_first_not_of(" \t\r\n\f\v") == std::string::npos
        || !validEmail(input.email) || input.senha.empty())
    {
        errorCallback(UsuarioError::InvalidInput);
        return;
    }

    // Repositories are copied: the calling service may expire before callbacks run.
    academias_.buscarPorId(input.academia_id,
        [input, callback, errorCallback, perfis = perfis_, usuarios = usuarios_]
        (const std::optional<models::Academia> &academia)
        {
            if (!academia) { errorCallback(UsuarioError::AcademiaNotFound); return; }
            if (!academia->ativo) { errorCallback(UsuarioError::AcademiaInactive); return; }
            perfis.buscarPorId(input.perfil_id,
                [input, callback, errorCallback, usuarios](const std::optional<models::Perfil> &perfil)
                {
                    if (!perfil) { errorCallback(UsuarioError::PerfilNotFound); return; }
                    if (perfil->ativo != 1) { errorCallback(UsuarioError::PerfilInactive); return; }
                    models::Usuario usuario;
                    usuario.academia_id = input.academia_id;
                    usuario.perfil_id = input.perfil_id;
                    usuario.nome = input.nome;
                    usuario.email = input.email;
                    try
                    {
                        usuario.senha_hash = security::PasswordHasher::hash(input.senha);
                    }
                    catch (...)
                    {
                        errorCallback(UsuarioError::Internal);
                        return;
                    }
                    // UNIQUE(academia_id, email) is the final concurrent duplicate guard.
                    usuarios.criar(usuario,
                        [usuarios, academiaId = input.academia_id, callback, errorCallback](std::int64_t id)
                        {
                            usuarios.buscarPorId(academiaId, id,
                                [callback, errorCallback](const std::optional<models::Usuario> &saved)
                                {
                                    if (saved) callback(*saved);
                                    else errorCallback(UsuarioError::Internal);
                                }, databaseError(errorCallback));
                        }, databaseError(errorCallback));
                }, databaseError(errorCallback));
        }, databaseError(errorCallback));
}

void UsuarioService::buscarPorId(std::int64_t academiaId, std::int64_t id,
                                 FindCallback callback, ErrorCallback errorCallback) const
{
    if (academiaId <= 0 || id <= 0) { errorCallback(UsuarioError::InvalidInput); return; }
    usuarios_.buscarPorId(academiaId, id,
        [callback, errorCallback](const std::optional<models::Usuario> &usuario)
        {
            if (usuario) callback(*usuario);
            else errorCallback(UsuarioError::NotFound);
        }, databaseError(errorCallback));
}

void UsuarioService::listarPorAcademia(std::int64_t academiaId, ListCallback callback,
                                       ErrorCallback errorCallback) const
{
    if (academiaId <= 0) { errorCallback(UsuarioError::InvalidInput); return; }
    usuarios_.listarPorAcademia(academiaId, std::move(callback), databaseError(errorCallback));
}
}
