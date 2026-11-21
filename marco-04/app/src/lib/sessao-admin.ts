/** O PIN do admin vale até o app ser fechado. */
let liberado = false;
export const adminLiberado = () => liberado;
export const liberarAdmin = () => { liberado = true; };
