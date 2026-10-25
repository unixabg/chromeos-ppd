#pragma once
#include <string>
class MetricsLibraryInterface { public: virtual ~MetricsLibraryInterface()=default; virtual bool SendToUMA(const std::string&, int, int, int, int){return true;} };
class MetricsLibrary : public MetricsLibraryInterface {};
