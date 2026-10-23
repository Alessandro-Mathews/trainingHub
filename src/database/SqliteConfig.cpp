#include "traininghub/database/SqliteConfig.h"

#include <drogon/orm/DbClient.h>
#include <sqlite3.h>
#include <mutex>
#include <stdexcept>

namespace traininghub::database
{
namespace
{
int enableForeignKeys(sqlite3 *db, char **error, const sqlite3_api_routines *)
{
    int enabled = 0;
    const auto result = sqlite3_db_config(db, SQLITE_DBCONFIG_ENABLE_FKEY, 1, &enabled);
    if (result == SQLITE_OK && enabled == 1)
    {
        // Wait on the SQLite worker, not the HTTP thread, for brief writer locks.
        return sqlite3_busy_timeout(db, 5000);
    }

    *error = sqlite3_mprintf("TrainingHub requires SQLite foreign_keys=ON");
    return result == SQLITE_OK ? SQLITE_ERROR : result;
}
}

void configureSqliteForeignKeys()
{
    static std::once_flag once;
    std::call_once(once, []
    {
        // Drogon 1.9.13 calls sqlite3_config(MULTITHREAD) once, before its first
        // open. sqlite3_auto_extension initializes SQLite, so registering first
        // would make that configuration fail with SQLITE_MISUSE. Warm up only
        // an isolated in-memory client, then register before any runtime client.
        auto bootstrap = drogon::orm::DbClient::newSqlite3Client("filename=:memory:", 1);
        bootstrap->setTimeout(5.0);
        bootstrap->execSqlSync("SELECT 1");
        bootstrap->closeAll();
        bootstrap.reset();

        // SQLite invokes this initializer on each open (also new pool clients).
        // Returning an error prevents opening an unprotected connection.
        if (sqlite3_auto_extension(reinterpret_cast<void (*)()>(enableForeignKeys)) != SQLITE_OK)
            throw std::runtime_error("Unable to register SQLite foreign key initialization");
    });
}

}
