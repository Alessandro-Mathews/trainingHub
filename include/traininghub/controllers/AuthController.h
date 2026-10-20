#pragma once

#include <drogon/HttpController.h>
#include <functional>

namespace traininghub::controllers
{

class AuthController : public drogon::HttpController<AuthController>
{
public:
    METHOD_LIST_BEGIN
    ADD_METHOD_TO(AuthController::login, "/api/auth/login", drogon::Post);
    ADD_METHOD_TO(AuthController::me, "/api/auth/me", drogon::Get);
    ADD_METHOD_TO(AuthController::logout, "/api/auth/logout", drogon::Post);
    METHOD_LIST_END

    void login(const drogon::HttpRequestPtr &req,
               std::function<void(const drogon::HttpResponsePtr &)> &&callback) const;
    void me(const drogon::HttpRequestPtr &req,
            std::function<void(const drogon::HttpResponsePtr &)> &&callback) const;
    void logout(const drogon::HttpRequestPtr &req,
                std::function<void(const drogon::HttpResponsePtr &)> &&callback) const;
};

}
