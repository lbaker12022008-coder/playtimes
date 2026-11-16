/**
 * Makes the one-off key pair that lets PlayTime send browser notifications.
 *
 * Run it once, from the project folder:
 *     node worker/make_vapid_keys.mjs
 *
 * It prints two values and then tells you the two commands to run. Nothing is
 * written to disk and nothing is sent anywhere - the keys only exist in what it
 * prints, so do this in a window you can close afterwards.
 *
 * The public key is handed out to browsers; the private key must only ever live in
 * Cloudflare, set with `wrangler secret put` so it is typed straight in rather than
 * passing through a file or a chat.
 *
 * No packages needed: this uses the WebCrypto built into Node 18 and later. (The
 * usual advice is `npx web-push generate-vapid-keys`, which downloads a package to
 * do the same arithmetic.)
 */
const b64url = bytes => Buffer.from(bytes).toString("base64")
  .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

const pair = await crypto.subtle.generateKey(
  { name: "ECDSA", namedCurve: "P-256" }, true, ["sign", "verify"]);

// 65 bytes: 0x04 then x then y. This is the form a browser's pushManager wants.
const publicKey = b64url(await crypto.subtle.exportKey("raw", pair.publicKey));
// The private scalar on its own, which is all push.js needs to rebuild the key.
const jwk = await crypto.subtle.exportKey("jwk", pair.privateKey);

console.log("");
console.log("VAPID_PUBLIC_KEY");
console.log("  " + publicKey);
console.log("");
console.log("VAPID_PRIVATE_KEY");
console.log("  " + jwk.d);
console.log("");
console.log("Now run these two commands and paste the matching value at each prompt:");
console.log("  npx wrangler secret put VAPID_PUBLIC_KEY");
console.log("  npx wrangler secret put VAPID_PRIVATE_KEY");
console.log("");
console.log("They take effect immediately - no deploy needed. Keep the private one to");
console.log("yourself; anyone who has it can send notifications to your readers.");
console.log("");
