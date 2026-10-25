#pragma once
#include "base/check.h"
#define DCHECK_NE(a,b) DCHECK((a)!=(b))
#define DCHECK_EQ(a,b) DCHECK((a)==(b))
#define DCHECK_GE(a,b) DCHECK((a)>=(b))
#define DCHECK_GT(a,b) DCHECK((a)>(b))
#define DCHECK_LT(a,b) DCHECK((a)<(b))
#define DCHECK_LE(a,b) DCHECK((a)<=(b))
