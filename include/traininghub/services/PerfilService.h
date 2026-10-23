#pragma once

#include "traininghub/repositories/PerfilRepository.h"

namespace traininghub::services
{

enum class PerfilError
{
    InvalidInput,
    NotFound,
    DuplicateName,
    InUse,
    Database
};

class PerfilService
{
public:
    using ErrorCallback = std::function<void(PerfilError)>;
    using SuccessCallback = std::function<void()>;
    using ListCallback = repositories::PerfilRepository::ListCallback;
    using FindCallback = std::function<void(const models::Perfil &)>;
    using CreateCallback = repositories::PerfilRepository::CreateCallback;

    explicit PerfilService(repositories::PerfilRepository repository);

    void listar(ListCallback callback, ErrorCallback errorCallback) const;
    void buscarPorId(std::int64_t id, FindCallback callback,
                     ErrorCallback errorCallback) const;
    void criar(const models::Perfil &perfil, CreateCallback callback,
               ErrorCallback errorCallback) const;
    void atualizar(std::int64_t id, const models::Perfil &perfil,
                   SuccessCallback callback, ErrorCallback errorCallback) const;
    void excluir(std::int64_t id, SuccessCallback callback,
                 ErrorCallback errorCallback) const;

private:
    repositories::PerfilRepository repository_;
};

}
