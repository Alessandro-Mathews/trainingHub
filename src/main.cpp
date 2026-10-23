#include <drogon/drogon.h>
#include "traininghub/database/SqliteConfig.h"

#include <exception>

int main()
{
    try
    {
        traininghub::database::configureSqliteForeignKeys();
        drogon::app()
            .loadConfigFile("config.json")
            .run();
    }
    catch (const std::exception &error)
    {
        LOG_ERROR << "Falha ao iniciar TrainingHub: " << error.what();
        return 1;
    }

    return 0;
}
