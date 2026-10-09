/** Select a DOM card locator only when unselected; resolves void, clicks normally, propagates locator errors. */
export async function ensureCardSelected(card) {
  const classes = (await card.getAttribute('class') ?? '').split(/\s+/);
  if (!classes.includes('selected')) await card.click();
}
