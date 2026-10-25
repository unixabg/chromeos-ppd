#pragma once
// Minimal stand-in for brillo::Process: fork, bind fds, PATH search, exec, wait.
#include <fcntl.h>
#include <functional>
#include <map>
#include <string>
#include <sys/wait.h>
#include <unistd.h>
#include <vector>
#include <dirent.h>
namespace brillo {
class Process {
 public:
  virtual ~Process() = default;
  void AddArg(const std::string& a) { args_.push_back(a); }
  void BindFd(int parent, int child) { binds_[child] = parent; }
  void SetCloseUnusedFileDescriptors(bool v) { close_unused_ = v; }
  void SetSearchPath(bool v) { search_ = v; }
  void SetPreExecCallback(std::function<bool()> cb) { pre_ = cb; }
  bool Start() {
    pid_ = fork();
    if (pid_ < 0) return false;
    if (pid_ == 0) {
      for (auto& [child, parent] : binds_) { if (parent != child) dup2(parent, child); }
      if (close_unused_) {
        for (int fd = 3; fd < 1024; ++fd) { if (!binds_.count(fd)) close(fd); }
      }
      if (pre_ && !pre_()) _exit(127);
      std::vector<char*> av;
      for (auto& s : args_) av.push_back(const_cast<char*>(s.c_str()));
      av.push_back(nullptr);
      if (search_) execvp(av[0], av.data()); else execv(av[0], av.data());
      perror("exec failed");
      _exit(127);
    }
    return true;
  }
  int Wait() {
    int st = 0;
    if (waitpid(pid_, &st, 0) < 0) return -1;
    if (WIFEXITED(st)) return WEXITSTATUS(st);
    if (WIFSIGNALED(st)) return 128 + WTERMSIG(st);
    return -1;
  }
 private:
  std::vector<std::string> args_;
  std::map<int, int> binds_;
  bool close_unused_ = false, search_ = false;
  std::function<bool()> pre_;
  pid_t pid_ = -1;
};
class ProcessImpl : public Process {};
}  // namespace brillo
