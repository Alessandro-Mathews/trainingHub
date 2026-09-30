#pragma once

#include "traininghub/repositories/AcademiaRepository.h"

namespace traininghub::services
{

class AcademiaService
{
public:
    explicit AcademiaService(repositories::AcademiaRepository repository);

    void listAll(
        repositories::AcademiaRepository::FindAllCallback callback,
        repositories::AcademiaRepository::ErrorCallback errorCallback
    ) const;

private:
    repositories::AcademiaRepository repository_;
};

}
