#pragma once
#include <functional>
namespace base {
template <class F, class... A> std::function<bool()> BindOnce(F f, A... a) { return [=]() { return f(a...); }; }
}
