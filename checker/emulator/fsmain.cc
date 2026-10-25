// Same behaviour as foomatic_shell/main.cc (-c script, -v, FOOMATIC_VERIFY_MODE).
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include "foomatic_shell/shell.h"
#include "metrics/metrics_library.h"
int main(int argc, char** argv) {
  const char* script = nullptr; bool verbose = false;
  bool verify = getenv("FOOMATIC_VERIFY_MODE") != nullptr;
  for (int i = 1; i < argc; ++i) { std::string p = argv[i];
    if (p == "-c" && i + 1 < argc) { script = argv[++i]; continue; }
    if (p == "-v") { verbose = true; continue; }
    if (p == "-e") continue;
    fprintf(stderr, "foomatic_shell: unknown parameter %s\n", p.c_str()); return -1; }
  if (!script) { fprintf(stderr, "foomatic_shell: -c required\n"); return -1; }
  if (strlen(script) > foomatic_shell::kMaxSourceSize) { fprintf(stderr, "script too large\n"); return -1; }
  MetricsLibrary m;
  return foomatic_shell::ExecuteShellScriptAndReportCpuTime(script, 1, verbose, verify, m);
}
