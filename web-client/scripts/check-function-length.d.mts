/** 单个超长函数的位置与有效行数。 */
export interface FunctionViolation {
  file: string;
  line: number;
  lines: number;
  name: string;
}

/** 检查内存中的 JS/TS 源码；输入文件名、源码与阈值，返回超限函数且无副作用。 */
export function inspectSource(file: string, source: string, limit?: number): FunctionViolation[];
