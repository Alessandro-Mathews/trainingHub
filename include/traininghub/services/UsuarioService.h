#pragma once

#include "traininghub/repositories/UsuarioRepository.h"
#include "traininghub/repositories/AcademiaRepository.h"
#include "traininghub/repositories/PerfilRepository.h"

namespace traininghub::services
{
enum class UsuarioError
{
    InvalidInput, NotFound, AcademiaNotFound, AcademiaInactive,
    PerfilNotFound, PerfilInactive, DuplicateEmail, RelationshipConflict, Internal
};

struct NovoUsuario
{
    std::int64_t academia_id{};
    std::int64_t perfil_id{};
    std::string nome;
    std::string email;
    std::string senha;
};

class UsuarioService
{
public:
    using ErrorCallback = std::function<void(UsuarioError)>;
    using FindCallback = std::function<void(const models::Usuario &)>;
    using ListCallback = repositories::UsuarioRepository::ListCallback;

    UsuarioService(repositories::UsuarioRepository usuarios,
                   repositories::AcademiaRepository academias,
                   repositories::PerfilRepository perfis);
    void criar(const NovoUsuario &input, FindCallback callback, ErrorCallback errorCallback) const;
    void buscarPorId(std::int64_t academiaId, std::int64_t id,
                     FindCallback callback, ErrorCallback errorCallback) const;
    void listarPorAcademia(std::int64_t academiaId, ListCallback callback,
                           ErrorCallback errorCallback) const;

private:
    repositories::UsuarioRepository usuarios_;
    repositories::AcademiaRepository academias_;
    repositories::PerfilRepository perfis_;
};
}
