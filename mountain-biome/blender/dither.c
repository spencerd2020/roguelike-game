/* Ramp-constrained Floyd-Steinberg error diffusion, serpentine.
 * t[i]   wanted position in the texel's own ramp, in ramp steps (0 .. n[i]-1), any float
 * n[i]   ramp length for the texel (0 = not a texel: skipped, takes and passes no error)
 * out[i] the chosen step
 * damp   share of the error passed on (0.8 to 1.0; lower is calmer)
 * Build: cc -O2 -shared -fPIC dither.c -o dither.so
 */
#include <math.h>
#include <stdlib.h>
void diffuse(const float *t, const int *n, int *out, int w, int h, float damp) {
    static float *err = 0; static long cap = 0;
    long N = (long)w * h;
    if (cap < N) { free(err); err = calloc(N, sizeof(float)); cap = N; }
    for (long i = 0; i < N; i++) err[i] = 0.f;
    for (int y = 0; y < h; y++) {
        int rev = y & 1;
        for (int k = 0; k < w; k++) {
            int x = rev ? w - 1 - k : k;
            long i = (long)y * w + x;
            if (n[i] <= 0) { out[i] = -1; continue; }
            float want = t[i] + err[i];
            int q = (int)floorf(want + 0.5f);
            if (q < 0) q = 0;
            if (q > n[i] - 1) q = n[i] - 1;
            out[i] = q;
            float e = (want - q) * damp;
            if (e > 1.f) e = 1.f; else if (e < -1.f) e = -1.f;
            int dx = rev ? -1 : 1;
            if (x + dx >= 0 && x + dx < w && n[i + dx] > 0) err[i + dx] += e * 7.f / 16.f;
            if (y + 1 < h) {
                long j = i + w;
                if (x - dx >= 0 && x - dx < w && n[j - dx] > 0) err[j - dx] += e * 3.f / 16.f;
                if (n[j] > 0) err[j] += e * 5.f / 16.f;
                if (x + dx >= 0 && x + dx < w && n[j + dx] > 0) err[j + dx] += e * 1.f / 16.f;
            }
        }
    }
}
