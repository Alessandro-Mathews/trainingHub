#include "traininghub/database/SqliteConfig.h"

#include <drogon/orm/DbClient.h>
#include <iostream>
#include <stdexcept>
#include <vector>

int main()
{
    try
    {
        traininghub::database::configureSqliteForeignKeys();
        traininghub::database::configureSqliteForeignKeys();
        for (int pool = 0; pool < 2; ++pool)
        {
            auto db = drogon::orm::DbClient::newSqlite3Client("filename=:memory:", 3);
            db->setTimeout(5.0);
            std::vector<std::shared_ptr<drogon::orm::Transaction>> connections;
            // Retaining each transaction pins a different physical connection.
            for (int connection = 0; connection < 3; ++connection)
            {
                auto transaction = db->newTransaction();
                const auto result = transaction->execSqlSync("PRAGMA foreign_keys");
                if (result.size() != 1 || result[0][0].as<int>() != 1)
                    throw std::runtime_error("foreign_keys must be ON on every Drogon connection");
                const auto timeout = transaction->execSqlSync("PRAGMA busy_timeout");
                if (timeout[0][0].as<int>() != 5000)
                    throw std::runtime_error("busy_timeout must be configured on every connection");
                connections.push_back(std::move(transaction));
            }
            connections.clear();
            db->closeAll();
        }
        std::cout << "foreign_keys=1 verified on 6 pinned Drogon connections in 2 pools.\n";
        return 0;
    }
    catch (const std::exception &error)
    {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
