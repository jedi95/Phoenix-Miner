// This file is taken and modified from the public-domain poclbm project, and
// we have therefore decided to keep it public-domain in Phoenix.

// 2011-07-17: further modified by Diapolo and still public-domain

#ifdef VECTORS
	typedef uint2 u;
#else
	typedef uint u;
#endif

__constant uint K[64] = { 
	0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
	0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
	0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
	0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
	0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
	0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
	0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
	0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
};

// H[6] =  0x08909ae5U + 0xb0edbdd0 + K[0] == 0xfc08884d
// H[7] = -0x5be0cd19 - (0x90befffa) K[60] == -0xec9fcd13
__constant uint H[8] = { 
	0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0xfc08884d, 0xec9fcd13
};

// L = 0xa54ff53a + 0xb0edbdd0 + K[0] == 0x198c7e2a2
__constant ulong L = 0x198c7e2a2;

// offset for W[] array to reduce it's size (W[0] - W[15] are hard-coded or computed without use of P() calculations)
#define O 15

#ifdef BITALIGN
	#pragma OPENCL EXTENSION cl_amd_media_ops : enable
	#define rot(x, y) amd_bitalign(x, x, (u)(32 - y))
#else
	#define rot(x, y) rotate(x, (u)y)
#endif

#ifdef BFI_INT
	#define Ch(x, y, z) amd_bytealign(x, y, z)
    #define Ma(z, x, y) amd_bytealign(z^x, y, x)
#else 
	#define Ch(x, y, z) bitselect(z, y, x)
    #define Ma(x, y, z) bitselect(x,y,(z^x))
#endif

// Various intermediate calculations for each SHA round
#define s0(n) (rot(Vals[(128 - n) % 8], 30) ^ rot(Vals[(128 - n) % 8], 19) ^ rot(Vals[(128 - n) % 8], 10))
#define s1(n) (rot(Vals[(132 - n) % 8], 26) ^ rot(Vals[(132 - n) % 8], 21) ^ rot(Vals[(132 - n) % 8], 7))
#define ch(n) (Ch(Vals[(132 - n) % 8], Vals[(133 - n) % 8], Vals[(134 - n) % 8]))
#define ma(n) (Ma(Vals[(129 - n) % 8], Vals[(130 - n) % 8], Vals[(128 - n) % 8]))
#define t1W(n) (K[n % 64] + Vals[(135 - n) % 8] + W[n - O] + s1(n) + ch(n))
#define t1(n) (K[n % 64] + Vals[(135 - n) % 8] + s1(n) + ch(n))

// intermediate W calculations
#define P1(x) (rot(W[x - 2 - O], 15) ^ rot(W[x - 2 - O], 13) ^ (W[x - 2 - O] >> 10U))
#define P2(x) (rot(W[x - 15 - O], 25) ^ rot(W[x - 15 - O], 14) ^ (W[x - 15 - O] >> 3U))
#define P3(x) W[x - 7 - O]
#define P4(x) W[x - 16 - O]

// full W calculation
#define W(x) (W[x - O] = P4(x) + P3(x) + P2(x) + P1(x))

// SHA round without W calc
#define sharoundW(n) { Vals[(131 - n) % 8] += t1W(n); Vals[(135 - n) % 8] = t1W(n) + s0(n) + ma(n); }
#define sharound(n) { Vals[(131 - n) % 8] += t1(n); Vals[(135 - n) % 8] = t1(n) + s0(n) + ma(n); }

// description of modified kernel init variables:
//
// C1addK5: C1addK5 = C1 + K[5]: C1addK5 = C1 + 0x59f111f1
// D1: D1 = D1 + K[4] + W[4]: D1 = D1 + 0xe9b5dba5 + 0x80000000U
// W2: W2 + W16 in P1(): W2 = P1(18) + P4(18)
// W17_2: 0x80000000U in P2() = 0x11002000 + W17 in P1(): W17_2 = P1(19) + P2(19)
// PreValaddT1: PreValaddT1 = PreVal4 + T1
// T1substate0: T1substate0 = T1 - substate0

__kernel void search(	const uint state0, const uint state1, const uint state2, const uint state3,
						const uint state4, const uint state5, const uint state6, const uint state7,
						const uint B1, const uint C1, const uint C1addK5, const uint D1,
						const uint F1, const uint G1, const uint H1,
						const uint base,
						const uint W2,
						const uint W16, const uint W17, const uint W17_2,
						const uint PreVal4addT1, const uint T1substate0,
						__global uint * output)
{
	u W[124 - O];
	u Vals[8];
#ifdef VECTORS
	u W_3 = ((base + get_global_id(0)) << 1) + (uint2)(0, 1);
#else
	u W_3 = base + get_global_id(0);
#endif
	u Temp;
	
	Vals[0] = W_3 + PreVal4addT1 + T1substate0;
	Vals[1] = B1;
	Vals[2] = C1;

	Vals[4] = W_3 + PreVal4addT1;
	Vals[5] = F1;
	Vals[6] = G1;
	
	// used in: P2(19) == 285220864 (0x11002000), P4(20)
	// W[4] = 0x80000000U;
	// P1(x) is 0 for x == 7, 8, 9, 10, 11, 12, 13, 14, 15, 16
	// P2(x) is 0 for x == 20, 21, 22, 23, 24, 25, 26, 27, 28, 29
	// P3(x) is 0 for x == 12, 13, 14, 15, 16, 17, 18, 19, 20, 21
	// P4(x) is 0 for x == 21, 22, 23, 24, 25, 26, 27, 28, 29, 30
	// W[x] in sharound(x) is 0 for x == 5, 6, 7, 8, 9, 10, 11, 12, 13, 14
	// W[14] = W[13] = W[12] = W[11] = W[10] = W[9] = W[8] = W[7] = W[6] = W[5] = 0x00000000U;
	// used in: P2(30) == 10485845 (0xA00055), P3(22), P4(31)
	// K[15] + W[15] == 0xc19bf174 + 0x00000280U = 0xc19bf3f4
	W[15 - O] = 0x00000280U;
	W[16 - O] = W16;
	W[17 - O] = W17;
	// P1(18) + P2(18) + P4(18)
	W[18 - O] = W2 + (rot(W_3, 25) ^ rot(W_3, 14) ^ (W_3 >> 3U));
	// P1(19) + P2(19) + P4(19)
	W[19 - O] = W_3 + W17_2;
	// P1(20) + P4(20)
	W[20 - O] = (u)0x80000000U + P1(20);
	W[21 - O] = P1(21);
	W[22 - O] = P1(22) + P3(22);
	W[23 - O] = P1(23) + P3(23);
	W[24 - O] = P1(24) + P3(24);
	W[25 - O] = P1(25) + P3(25);
	W[26 - O] = P1(26) + P3(26);
	W[27 - O] = P1(27) + P3(27);
	W[28 - O] = P1(28) + P3(28);
	W[29 - O] = P1(29) + P3(29);
	W[30 - O] = (u)0xA00055 + P1(30) + P3(30);
	
	// Round 4
	Temp = D1 + ch(4) + s1(4);
	Vals[7] = Temp + H1;
	Vals[3] = Temp + ma(4) + s0(4);	

	// Round 5
	Temp = C1addK5 + ch(5) + s1(5);
	Vals[6] = Temp + G1;
	Vals[2] = Temp + ma(5) + s0(5);

	// W[] is zero for this rounds
	sharound(6);
	sharound(7);
	sharound(8);
	sharound(9);
	sharound(10);
	sharound(11);
	sharound(12);
	sharound(13);
	sharound(14);

	sharoundW(15);
	sharoundW(16);
	sharoundW(17);
	sharoundW(18);
	sharoundW(19);
	sharoundW(20);
	sharoundW(21);
	sharoundW(22);
	sharoundW(23);
	sharoundW(24);
	sharoundW(25);
	sharoundW(26);
	sharoundW(27);
	sharoundW(28);
	sharoundW(29);
	sharoundW(30);

	W(31);
	sharoundW(31);
	W(32);
	sharoundW(32);
	W(33);
	sharoundW(33);
	W(34);
	sharoundW(34);
	W(35);
	sharoundW(35);
	W(36);
	sharoundW(36);
	W(37);
	sharoundW(37);
	W(38);
	sharoundW(38);
	W(39);
	sharoundW(39);
	W(40);
	sharoundW(40);
	W(41);
	sharoundW(41);
	W(42);
	sharoundW(42);
	W(43);
	sharoundW(43);
	W(44);
	sharoundW(44);
	W(45);
	sharoundW(45);
	W(46);
	sharoundW(46);
	W(47);
	sharoundW(47);
	W(48);
	sharoundW(48);
	W(49);
	sharoundW(49);
	W(50);
	sharoundW(50);
	W(51);
	sharoundW(51);
	W(52);
	sharoundW(52);
	W(53);
	sharoundW(53);
	W(54);
	sharoundW(54);
	W(55);
	sharoundW(55);
	W(56);
	sharoundW(56);
	W(57);
	sharoundW(57);
	W(58);
	sharoundW(58);
	W(59);
	sharoundW(59);
	W(60);
	sharoundW(60);
	W(61);
	sharoundW(61);
	W(62);
	sharoundW(62);
	W(63);
	sharoundW(63);

	W[64 - O] = state0 + Vals[0];
	W[65 - O] = state1 + Vals[1];
	W[66 - O] = state2 + Vals[2];
	W[67 - O] = state3 + Vals[3];
	W[68 - O] = state4 + Vals[4];
	W[69 - O] = state5 + Vals[5];
	W[70 - O] = state6 + Vals[6];
	W[71 - O] = state7 + Vals[7];
	// used in: P2(87) = 285220864 (0x11002000), P4(88)
	// K[72] + W[72] ==
	W[72 - O] = 0x80000000U;
	// P1(x) is 0 for x == 75, 76, 77, 78, 79, 80
	// P2(x) is 0 for x == 88, 89, 90, 91, 92, 93
	// P3(x) is 0 for x == 80, 81, 82, 83, 84, 85
	// P4(x) is 0 for x == 89, 90, 91, 92, 93, 94
	// W[x] in sharound(x) is 0 for x == 73, 74, 75, 76, 77, 78
	// W[78] = W[77] = W[76] = W[75] = W[74] = W[73] = 0x00000000U;
	// used in: P1(81) = 10485760 (0xA00000), P2(94) = 4194338 (0x400022), P3(86), P4(95)
	// K[79] + W[79] ==
	W[79 - O] = 0x00000100U;

	Vals[0] = H[0];
	Vals[1] = H[1];
	Vals[2] = H[2];
	Vals[3] = (u)L + W[64 - O];
	Vals[4] = H[3];
	Vals[5] = H[4];
	Vals[6] = H[5];
	Vals[7] = H[6] + W[64 - O];
	
	sharoundW(65);
	sharoundW(66);
	sharoundW(67);
	sharoundW(68);
	sharoundW(69);
	sharoundW(70);
	sharoundW(71);
	sharoundW(72);

	// W[] is zero for this rounds
	sharound(73);
	sharound(74);
	sharound(75);
	sharound(76);
	sharound(77);
	sharound(78);

	sharoundW(79);
	
	W[80 - O] = P2(80) + P4(80);
	W[81 - O] = (u)0xA00000 + P4(81) + P2(81);
	W[82 - O] = P4(82) + P2(82) + P1(82);
	W[83 - O] = P4(83) + P2(83) + P1(83);
	W[84 - O] = P4(84) + P2(84) + P1(84);
	W[85 - O] = P4(85) + P2(85) + P1(85);
	W(86);

	sharoundW(80);
	sharoundW(81);	
	sharoundW(82);
	sharoundW(83);
	sharoundW(84);
	sharoundW(85);
	sharoundW(86);

	W[87 - O] = (u)0x11002000 + P4(87) + P3(87) + P1(87);
	sharoundW(87);
	W[88 - O] = (u)0x80000000U + P3(88) + P1(88);
	sharoundW(88);
	W[89 - O] = P3(89) + P1(89);
	sharoundW(89);
	W[90 - O] = P3(90) + P1(90);
	sharoundW(90);
	W[91 - O] = P3(91) + P1(91);
	sharoundW(91);
	W[92 - O] = P3(92) + P1(92);
	sharoundW(92);
	W[93 - O] = P3(93) + P1(93);
	sharoundW(93);
	W[94 - O] = (u)0x400022 + P3(94) + P1(94);
	sharoundW(94);
	W[95 - O] = (u)0x00000100U + P3(95) + P2(95) + P1(95);
	sharoundW(95);

	W(96);
	sharoundW(96);
	W(97);
	sharoundW(97);
	W(98);
	sharoundW(98);
	W(99);
	sharoundW(99);
	W(100);
	sharoundW(100);
	W(101);
	sharoundW(101);
	W(102);
	sharoundW(102);
	W(103);
	sharoundW(103);
	W(104);
	sharoundW(104);
	W(105);
	sharoundW(105);
	W(106);
	sharoundW(106);
	W(107);
	sharoundW(107);
	W(108);
	sharoundW(108);
	W(109);
	sharoundW(109);
	W(110);
	sharoundW(110);
	W(111);
	sharoundW(111);
	W(112);
	sharoundW(112);
	W(113);
	sharoundW(113);
	W(114);
	sharoundW(114);
	W(115);
	sharoundW(115);
	W(116);
	sharoundW(116);
	W(117);
	sharoundW(117);
	W(118);
	sharoundW(118);
	W(119);
	sharoundW(119);
	W(120);
	sharoundW(120);
	W(121);
	sharoundW(121);
	W(122);
	sharoundW(122);
	W(123);
	sharoundW(123);

	// Round 124
	Vals[7] += Vals[3] + P4(124) + P3(124) + P2(124) + P1(124) + s1(124) + ch(124);
	
#ifdef VECTORS
	if(Vals[7].x == -H[7])
	{	
		output[OUTPUT_SIZE] = output[(W[3].x >> 2) & OUTPUT_MASK] = W_3.x;
	}
	if(Vals[7].y == -H[7])
	{
		output[OUTPUT_SIZE] = output[(W[3].y >> 2) & OUTPUT_MASK] =  W_3.y;
	}
#else
	if(Vals[7] == -H[7])
	{
		output[OUTPUT_SIZE] = output[(W[3] >> 2) & OUTPUT_MASK] = W_3;
	}
#endif
}