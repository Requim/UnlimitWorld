/** 创建可手动完成的测试 Promise；返回 promise/resolve/reject，仅测试控制异步完成顺序。 */
export function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (cause: unknown) => void;
  const promise = new Promise<T>((accept, fail) => { resolve = accept; reject = fail; });
  return { promise, resolve, reject };
}
