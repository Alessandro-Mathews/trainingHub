#include "traininghub/services/AcademiaService.h"

#include <utility>

namespace traininghub::services
{

AcademiaService::AcademiaService(repositories::AcademiaRepository repository)
    : repository_(std::move(repository))
{
}

void AcademiaService::listAll(
    repositories::AcademiaRepository::FindAllCallback callback,
    repositories::AcademiaRepository::ErrorCallback errorCallback
) const
{
    repository_.findAll(std::move(callback), std::move(errorCallback));
}

}
