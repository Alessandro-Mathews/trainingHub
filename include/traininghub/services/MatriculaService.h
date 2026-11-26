#pragma once

#include "traininghub/repositories/MatriculaRepository.h"
#include "traininghub/security/ValidatedAuthContext.h"

namespace traininghub::services
{
enum class MatriculaError
{
    InvalidInput, Unauthorized, Forbidden, ResourcesNotFound, NotFound, AlunoNotFound,
    IneligibleAluno, InactivePlano, InvalidValidity, RelationshipConflict, Internal
};

struct NovaMatricula
{
    std::int64_t alunoId{};
    std::int64_t planoId{};
};

class MatriculaService
{
public:
    using ErrorCallback = std::function<void(MatriculaError)>;
    using FindCallback = std::function<void(const models::Matricula &)>;
    using ListCallback = repositories::MatriculaRepository::ListCallback;

    explicit MatriculaService(repositories::MatriculaRepository repository);
    void criar(const security::ValidatedAuthContext &actor, const NovaMatricula &input,
        FindCallback callback, ErrorCallback errorCallback) const;
    void listarPorAcademia(const security::ValidatedAuthContext &actor, ListCallback callback,
        ErrorCallback errorCallback) const;
    void buscarPorId(const security::ValidatedAuthContext &actor, std::int64_t id,
        FindCallback callback, ErrorCallback errorCallback) const;
    void listarPorAluno(const security::ValidatedAuthContext &actor, std::int64_t alunoId,
        ListCallback callback, ErrorCallback errorCallback) const;

private:
    repositories::MatriculaRepository repository_;
};
}
