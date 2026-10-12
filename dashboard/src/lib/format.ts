import { CURRENCY } from '../config/market';
export const number = (value: number, digits = 1) =>
  new Intl.NumberFormat('fr-FR', {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(value);
export const money = (value: number) => `${number(value, 2)} ${CURRENCY}`;
export const dateTime = (value: number) =>
  new Intl.DateTimeFormat('fr-FR', {
    timeZone: 'UTC',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
    .format(value);
export const time = (value: number) =>
  new Intl.DateTimeFormat('fr-FR', { timeZone: 'UTC', hour: '2-digit', minute: '2-digit' }).format(
    value,
  );
export const shortDate = (value: number) =>
  new Intl.DateTimeFormat('fr-FR', { timeZone: 'UTC', day: '2-digit', month: '2-digit' }).format(
    value,
  );
