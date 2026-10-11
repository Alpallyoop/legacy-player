"""The pure-Python cryptography behind end-to-end encrypted friends messages and the console's two-factor login,
checked against the RFC test vectors, plus the envelope format, its commitment and the safety code."""
import hashlib
import unittest

from server.social import e2e, qr
from server.social import purecrypto as pc

H = bytes.fromhex


class X25519(unittest.TestCase):
    """RFC 7748 sections 5.2 and 6.1."""

    def test_function_vectors(self):
        self.assertEqual(H("c3da55379de9c6908e94ea4df28d084f32eccf03491c71f754b4075577a28552"),
                         pc.x25519(H("a546e36bf0527c9d3b16154b82465edd62144c0ac1fc5a18506a2244ba449ac4"),
                                   H("e6db6867583030db3594c1a424b15f7c726624ec26b3353b10a903a6d0ab1c4c")))
        self.assertEqual(H("95cbde9476e8907d7aade45cb4b873f88b595a68799fa152e6f8f7647aac7957"),
                         pc.x25519(H("4b66e9d4d1b4673c5ad22691957d6af5c11b6421e0ea01d42ca4169e7918ba0d"),
                                   H("e5210f12786811d3f4b7959d0538ae2c31dbe7106fc03c3efc4cd549c715a493")))

    def test_iterated_vectors(self):
        k = u = pc.BASE_POINT
        results = {}
        for i in range(1, 1001):
            k, u = pc.x25519(k, u), k
            if i in (1, 1000):
                results[i] = k.hex()
        self.assertEqual("422c8e7a6227d7bca1350b3e2bb7279f7897b87bb6854b783c60e80311ae3079", results[1])
        self.assertEqual("684cf59ba83309552800ef566f2f4d3c1c3887c49360e3875f2eb94d99532c51", results[1000])

    def test_diffie_hellman(self):
        a = H("77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a")
        b = H("5dab087e624a8a4b79e17f8b83800ee66f3bb1292618b6fd1c2f8b27ff88e0eb")
        a_pub, b_pub = pc.x25519_keypair(a)[1], pc.x25519_keypair(b)[1]
        self.assertEqual("8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a", a_pub.hex())
        self.assertEqual("de9edb7d7b7dc1b4d35b61c2ece435373f8343c85b78674dadfc7e146f882b4f", b_pub.hex())
        shared = "4a5d9d5ba4ce2de1728e3bf480350f25e07e21c947d19e3376f09b3c1e161742"
        self.assertEqual(shared, pc.shared_secret(a, b_pub).hex())
        self.assertEqual(shared, pc.shared_secret(b, a_pub).hex())

    def test_a_small_order_key_is_refused(self):
        with self.assertRaises(ValueError):
            pc.shared_secret(pc.x25519_keypair()[0], b"\x00" * 32)


class ChaCha20Poly1305(unittest.TestCase):
    """RFC 8439 sections 2.3.2, 2.4.2, 2.5.2 and 2.8.2."""
    KEY = bytes(range(32))
    SUNSCREEN = (b"Ladies and Gentlemen of the class of '99: If I could offer you only one tip for the future, "
                 b"sunscreen would be it.")

    def test_block_function(self):
        self.assertEqual(H("10f1e7e4d13b5915500fdd1fa32071c4c7d1f4c733c068030422aa9ac3d46c4e"
                           "d2826446079faa0914c2d705d98b02a2b5129cd1de164eb9cbd083e8a2503c4e"),
                         pc.chacha20_block(self.KEY, 1, H("000000090000004a00000000")))

    def test_encryption(self):
        expected = H("6e2e359a2568f98041ba0728dd0d6981e97e7aec1d4360c20a27afccfd9fae0bf91b65c5524733ab8f593dabcd62b357"
                     "1639d624e65152ab8f530c359f0861d807ca0dbf500d6a6156a38e088a22b65e52bc514d16ccf806818ce91ab7793736"
                     "5af90bbf74a35be6b40b8eedf2785e42874d")
        nonce = H("000000000000004a00000000")
        self.assertEqual(expected, pc.chacha20_xor(self.KEY, 1, nonce, self.SUNSCREEN))
        self.assertEqual(self.SUNSCREEN, pc.chacha20_xor(self.KEY, 1, nonce, expected))

    def test_poly1305(self):
        key = H("85d6be7857556d337f4452fe42d506a80103808afb0db2fd4abff6af4149f51b")
        self.assertEqual("a8061dc1305136c6c22b8baf0c0127a9", pc.poly1305(key, b"Cryptographic Forum Research Group").hex())

    def test_aead(self):
        key = bytes(range(0x80, 0xA0))
        nonce = H("070000004041424344454647")
        aad = H("50515253c0c1c2c3c4c5c6c7")
        sealed = pc.aead_encrypt(key, nonce, self.SUNSCREEN, aad)
        self.assertEqual(H("d31a8d34648e60db7b86afbc53ef7ec2a4aded51296e08fea9e2b5a736ee62d63dbea45e8ca9671282fafb69da92728b"
                           "1a71de0a9e060b2905d6a5b67ecd3b3692ddbd7f2d778b8c9803aee328091b58fab324e4fad675945585808b4831d7bc"
                           "3ff4def08e4b7a9de576d26586cec64b6116"), sealed[:-16])
        self.assertEqual("1ae10b594f09e26a7e902ecbd0600691", sealed[-16:].hex())
        self.assertEqual(self.SUNSCREEN, pc.aead_decrypt(key, nonce, sealed, aad))
        for bad in (sealed[:-1] + bytes([sealed[-1] ^ 1]), bytes([sealed[0] ^ 1]) + sealed[1:]):
            with self.assertRaises(pc.AuthError):
                pc.aead_decrypt(key, nonce, bad, aad)
        with self.assertRaises(pc.AuthError):
            pc.aead_decrypt(key, nonce, sealed, aad + b"x")


class HKDF(unittest.TestCase):
    """RFC 5869 appendix A.1 to A.3 (SHA-256)."""

    def test_vectors(self):
        self.assertEqual("3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865",
                         pc.hkdf(b"\x0b" * 22, bytes(range(13)), bytes(range(0xF0, 0xFA)), 42).hex())
        self.assertEqual("b11e398dc80327a1c8e7f78c596a49344f012eda2d4efad8a050cc4c19afa97c59045a99cac7827271cb41c65e590e09"
                         "da3275600c2f09b8367793a9aca3db71cc30c58179ec3e87c14c01d5c1f3434f1d87",
                         pc.hkdf(bytes(range(0x00, 0x50)), bytes(range(0x60, 0xB0)), bytes(range(0xB0, 0x100)), 82).hex())
        self.assertEqual("8da4e775a563c18f715f802a063c5a31b8a11f5c5ee1879ec3454e5f3c738d2d9d201395faa4b61a96c8",
                         pc.hkdf(b"\x0b" * 22, b"", b"", 42).hex())
        self.assertEqual("077709362c2e32df0ddc3f0dc47bba6390b6c73bb50f9c3122ec844ad7c2b3e5",
                         pc.hkdf_extract(bytes(range(13)), b"\x0b" * 22).hex())


class TOTP(unittest.TestCase):
    """RFC 6238 appendix B (8 digits, SHA-1 / SHA-256 / SHA-512)."""
    SEEDS = {"sha1": b"12345678901234567890", "sha256": b"12345678901234567890123456789012",
             "sha512": b"1234567890123456789012345678901234567890123456789012345678901234"}
    TABLE = [(59, "94287082", "46119246", "90693936"), (1111111109, "07081804", "68084774", "25091201"),
             (1111111111, "14050471", "67062674", "99943326"), (1234567890, "89005924", "91819424", "93441116"),
             (2000000000, "69279037", "90698825", "38618901"), (20000000000, "65353130", "77737706", "47863826")]

    def test_vectors(self):
        for t, s1, s256, s512 in self.TABLE:
            self.assertEqual(s1, pc.totp(self.SEEDS["sha1"], t, 8, hash_name="sha1"), t)
            self.assertEqual(s256, pc.totp(self.SEEDS["sha256"], t, 8, hash_name="sha256"), t)
            self.assertEqual(s512, pc.totp(self.SEEDS["sha512"], t, 8, hash_name="sha512"), t)

    def test_matching_allows_one_step_of_drift(self):
        secret = pc.totp_secret_bytes(pc.new_totp_secret())
        now = 1_700_000_000
        self.assertEqual(now // 30, pc.totp_match(secret, pc.totp(secret, now), now))
        self.assertEqual(now // 30 - 1, pc.totp_match(secret, pc.totp(secret, now - 30), now))
        self.assertEqual(now // 30 + 1, pc.totp_match(secret, pc.totp(secret, now + 30), now))
        self.assertIsNone(pc.totp_match(secret, pc.totp(secret, now - 90), now))
        self.assertIsNone(pc.totp_match(secret, "12345", now))
        uri = pc.otpauth_uri("JBSWY3DPEHPK3PXP", "alec", "Legacy Player friends")
        self.assertTrue(uri.startswith("otpauth://totp/Legacy%20Player%20friends%3Aalec?secret=JBSWY3DPEHPK3PXP&"))


class Envelopes(unittest.TestCase):
    def setUp(self):
        self.a = pc.x25519_keypair()
        self.b = pc.x25519_keypair()
        self.c = pc.x25519_keypair()
        self.conv = e2e.direct_conv("alice", "bob")

    def seal(self, text="see you at 8"):
        return e2e.seal(*self.a, "alice", self.conv, {"alice": self.a[1], "bob": self.b[1]}, text)

    def test_both_ends_open_it_and_nobody_else(self):
        env = self.seal()
        self.assertNotIn("see you", repr(env))
        self.assertEqual("see you at 8", e2e.open_envelope(env, "bob", *self.b)[0])
        self.assertEqual("see you at 8", e2e.open_envelope(env, "alice", *self.a)[0])     # the sender's own copy
        with self.assertRaises(e2e.E2EError):
            e2e.open_envelope(env, "carol", *self.c)
        with self.assertRaises(e2e.E2EError):
            e2e.open_envelope(env, "bob", *self.c)                                            # bob's slot, someone else's key

    def test_a_revealed_key_opens_exactly_that_message(self):
        env, other = self.seal(), self.seal("something else")
        key = e2e.unwrap(env, "bob", *self.b)
        self.assertEqual("see you at 8", e2e.open_with_key(env, key, self.conv, "alice"))
        with self.assertRaises(e2e.E2EError):
            e2e.open_with_key(other, key, self.conv, "alice")                                 # another message's key
        with self.assertRaises(e2e.E2EError):
            e2e.open_with_key(env, pc.random_bytes(32), self.conv, "alice")                   # a made-up key
        with self.assertRaises(e2e.E2EError):
            e2e.open_with_key(env, key, self.conv, "bob")                                     # claimed by someone else
        with self.assertRaises(e2e.E2EError):
            e2e.open_with_key(env, key, e2e.direct_conv("alice", "carol"), "alice")           # moved to another conversation

    def test_tampering_is_caught(self):
        env = self.seal()
        c = bytearray(pc.b64d(env["c"]))
        c[0] ^= 1
        with self.assertRaises(e2e.E2EError):
            e2e.open_envelope(dict(env, c=pc.b64e(bytes(c))), "bob", *self.b)
        with self.assertRaises(e2e.E2EError):
            e2e.open_envelope(dict(env, kc=pc.b64e(b"\x00" * 32)), "bob", *self.b)

    def test_the_service_checks_the_shape(self):
        env = self.seal()
        members = {"alice": pc.b64e(self.a[1]), "bob": pc.b64e(self.b[1])}
        clean = e2e.check_shape(env, "alice", self.conv, pc.b64e(self.a[1]), members)
        self.assertEqual(env["c"], clean["c"])
        for bad_args in ((env, "bob", self.conv, pc.b64e(self.a[1]), members),                   # not from the sender
                         (env, "alice", "d:x:y", pc.b64e(self.a[1]), members),                    # another conversation
                         (env, "alice", self.conv, pc.b64e(self.c[1]), members),                  # not the sender's key
                         (env, "alice", self.conv, pc.b64e(self.a[1]), {**members, "carol": pc.b64e(self.c[1])}),
                         ({"text": "plain"}, "alice", self.conv, pc.b64e(self.a[1]), members)):
            with self.assertRaises(e2e.E2EError):
                e2e.check_shape(*bad_args)

    def test_safety_code_is_the_same_both_ways_and_changes_with_a_key(self):
        one = e2e.safety_code("alice", self.a[1], "bob", self.b[1])
        self.assertEqual(one, e2e.safety_code("bob", self.b[1], "alice", self.a[1]))
        self.assertRegex(one, r"^\d{5} \d{5} \d{5} \d{5}$")
        self.assertNotEqual(one, e2e.safety_code("alice", self.a[1], "bob", self.c[1]))


class QRCodes(unittest.TestCase):
    """Finished symbols compared with ones made by Project Nayuki's reference QR Code generator (qrcodegen 1.8.0)."""
    REFERENCE = [
        ("hello", "M", 21, "99ccedcf0d82e92a63894c8b42e405a3ac50eafa33ee2ce68fa895813fdcb386"),
        ("otpauth://totp/Legacy%20Player%20friends%3Aalec?secret=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP&issuer=Legacy%20Player%20friends"
         "&algorithm=SHA1&digits=6&period=30", "M", 53, "990c7c6a9dd63a4e645290cd1ba04a1d81476d72785c2cd11b906e7aa50581cc"),
        ("x" * 200, "L", 53, "cfe4fcc3cbfb75bae459f5b5755931f4e90efa22627918ac07302a383974300e"),
        ("A" * 300, "M", 69, "55a53aef10cfd580a8f8622a199bd63a3763fb7f3f53e7d754e9fe748d6140b5"),
    ]

    def test_symbols_match_the_reference_generator(self):
        for text, ecl, size, digest in self.REFERENCE:
            rows = qr.encode(text, ecl)
            self.assertEqual(size, len(rows), text[:20])
            bits = "".join("1" if v else "0" for row in rows for v in row)
            self.assertEqual(digest, hashlib.sha256(bits.encode()).hexdigest(), text[:20])

    def test_svg_and_limits(self):
        image = qr.svg("otpauth://totp/x?secret=ABC")
        self.assertTrue(image.startswith("<svg") and image.endswith("</svg>"))
        self.assertNotIn("<script", image)
        with self.assertRaises(qr.QRError):
            qr.encode("x" * 5000)


if __name__ == "__main__":
    unittest.main()
