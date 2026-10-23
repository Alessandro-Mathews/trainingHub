#pragma once

namespace traininghub::database
{

// Call before creating application DbClients. Applies to every future connection.
void configureSqliteForeignKeys();

}
