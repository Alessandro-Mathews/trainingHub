#pragma once

#include "traininghub/repositories/PlanoRepository.h"
#include "traininghub/security/ValidatedAuthContext.h"

namespace traininghub::services
{
enum class PlanoError
{
    InvalidInput, Unauthorized, Forbidden, NotFound, DuplicateName, RelationshipConflict, Internal
};

struct DadosPlano
{
    std::string nome;
    std::optional<std::string> descricao;
    std::int64_t valorCentavos{};
    std::int64_t duracaoDias{};
};

class PlanoService
{
public:
    using ErrorCallback = std::function<void(PlanoError)>;
    using FindCallback = std::function<void(const models::Plano &)>;
    using ListCallback = repositories::PlanoRepository::ListCallback;

    explicit PlanoService(repositories::PlanoRepository repository);
    void criar(const security::ValidatedAuthContext &actor, const DadosPlano &dados,
        FindCallback callback, ErrorCallback errorCallback) const;
    void listarPorAcademia(const security::ValidatedAuthContext &actor, ListCallback callback,
        ErrorCallback errorCallback) const;
    void buscarPorId(const security::ValidatedAuthContext &actor, std::int64_t id,
        FindCallback callback, ErrorCallback errorCallback) const;
    void atualizar(const security::ValidatedAuthContext &actor, std::int64_t id,
        const DadosPlano &dados, FindCallback callback, ErrorCallback errorCallback) const;
    void atualizarStatus(const security::ValidatedAuthContext &actor, std::int64_t id,
        bool ativo, FindCallback callback, ErrorCallback errorCallback) const;

private:
    repositories::PlanoRepository repository_;
};
}
