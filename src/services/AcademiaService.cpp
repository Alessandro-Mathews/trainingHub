#include "traininghub/services/AcademiaService.h"

#include <utility>

namespace traininghub::services
{

AcademiaService::AcademiaService(repositories::AcademiaRepository repository)
    : repository_(std::move(repository))
{
}

void AcademiaService::listarPorAcademia(std::int64_t academiaId,
    repositories::AcademiaRepository::FindAllCallback callback,
    repositories::AcademiaRepository::ErrorCallback errorCallback
) const
{
    repository_.buscarPorId(academiaId,
        [callback = std::move(callback)](const std::optional<models::Academia> &academia)
        {
            callback(academia ? std::vector<models::Academia>{*academia}
                             : std::vector<models::Academia>{});
        }, std::move(errorCallback));
}

}
