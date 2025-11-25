from django.core.management.base import BaseCommand
from brackets.models import Bracket, GroupStage, KnockoutStage, User


class Command(BaseCommand):
    help = 'Seeds the 2026 FIFA World Cup bracket structure'

    def _teams_to_bit_vector(self, third_place_teams):
        """
        Convert a list of third-place teams to a bit vector.
        Each group A-L is represented by a bit position (A=0, B=1, ..., L=11).

        Example: ['3B', '3C', '3E'] -> 0b000000010110 = 22
        """
        group_to_bit = {
            '3A': 0, '3B': 1, '3C': 2, '3D': 3,
            '3E': 4, '3F': 5, '3G': 6, '3H': 7,
            '3I': 8, '3J': 9, '3K': 10, '3L': 11
        }

        bit_vector = 0
        for team in third_place_teams:
            if team in group_to_bit:
                bit_vector |= (1 << group_to_bit[team])

        return bit_vector

    def _get_third_place_combinations_data(self):
        """Get the raw third-place combinations data (FIFA 2026 regulations)."""
        # First place teams that will play third-place teams in R32
        first_place_teams = ['1A', '1B', '1D', '1E', '1G', '1I', '1K', '1L']

        # Raw data: option_number followed by 8 third-place teams
        # Format matches order of first_place_teams above
        raw_data = """
19 3C 3J 3I 3D 3H 3F 3L 3K
20 3C 3G 3I 3D 3J 3F 3L 3K
21 3C 3G 3J 3D 3H 3F 3L 3K
22 3C 3G 3I 3D 3H 3F 3L 3K
23 3C 3G 3J 3D 3H 3F 3L 3I
24 3C 3G 3J 3D 3H 3F 3I 3K
25 3E 3J 3I 3C 3H 3D 3L 3K
26 3E 3G 3I 3C 3J 3D 3L 3K
27 3E 3G 3J 3C 3H 3D 3L 3K
28 3E 3G 3I 3C 3H 3D 3L 3K
29 3E 3G 3J 3C 3H 3D 3L 3I
1 3E 3J 3I 3F 3H 3G 3L 3K
30 3E 3G 3J 3C 3H 3D 3I 3K
2 3H 3G 3I 3D 3J 3F 3L 3K
31 3C 3J 3E 3D 3I 3F 3L 3K
3 3E 3J 3I 3D 3H 3G 3L 3K
32 3C 3J 3E 3D 3H 3F 3L 3K
4 3E 3J 3I 3D 3H 3F 3L 3K
33 3C 3E 3I 3D 3H 3F 3L 3K
5 3E 3G 3I 3D 3J 3F 3L 3K
34 3C 3J 3E 3D 3H 3F 3L 3I
6 3E 3G 3J 3D 3H 3F 3L 3K
35 3C 3J 3E 3D 3H 3F 3I 3K
7 3E 3G 3I 3D 3H 3F 3L 3K
36 3C 3G 3E 3D 3J 3F 3L 3K
8 3E 3G 3J 3D 3H 3F 3L 3I
37 3C 3G 3E 3D 3I 3F 3L 3K
9 3E 3G 3J 3D 3H 3F 3I 3K
38 3C 3G 3E 3D 3J 3F 3L 3I
10 3H 3G 3I 3C 3J 3F 3L 3K
39 3C 3G 3E 3D 3J 3F 3I 3K
11 3E 3J 3I 3C 3H 3G 3L 3K
40 3C 3G 3E 3D 3H 3F 3L 3K
12 3E 3J 3I 3C 3H 3F 3L 3K
41 3C 3G 3J 3D 3H 3F 3L 3E
13 3E 3G 3I 3C 3J 3F 3L 3K
42 3C 3G 3J 3D 3H 3F 3E 3K
14 3E 3G 3J 3C 3H 3F 3L 3K
43 3C 3G 3E 3D 3H 3F 3L 3I
15 3E 3G 3I 3C 3H 3F 3L 3K
44 3C 3G 3E 3D 3H 3F 3I 3K
16 3E 3G 3J 3C 3H 3F 3L 3I
45 3C 3G 3J 3D 3H 3F 3E 3I
17 3E 3G 3J 3C 3H 3F 3I 3K
46 3H 3J 3B 3F 3I 3G 3L 3K
18 3H 3G 3I 3C 3J 3D 3L 3K
47 3E 3J 3I 3B 3H 3G 3L 3K
48 3E 3J 3B 3F 3I 3H 3L 3K
77 3H 3G 3B 3D 3J 3F 3L 3E
49 3E 3J 3B 3F 3I 3G 3L 3K
78 3H 3G 3B 3D 3J 3F 3E 3K
50 3E 3J 3B 3F 3H 3G 3L 3K
79 3E 3G 3B 3D 3H 3F 3L 3I
51 3E 3G 3B 3F 3I 3H 3L 3K
80 3E 3G 3B 3D 3H 3F 3I 3K
52 3E 3J 3B 3F 3H 3G 3L 3I
81 3H 3G 3B 3D 3J 3F 3E 3I
53 3E 3J 3B 3F 3H 3G 3I 3K
82 3H 3J 3B 3C 3I 3G 3L 3K
54 3H 3J 3B 3D 3I 3G 3L 3K
83 3H 3J 3B 3C 3I 3F 3L 3K
55 3H 3J 3B 3D 3I 3F 3L 3K
84 3I 3G 3B 3C 3J 3F 3L 3K
56 3I 3G 3B 3D 3J 3F 3L 3K
85 3H 3G 3B 3C 3J 3F 3L 3K
57 3H 3G 3B 3D 3J 3F 3L 3K
86 3H 3G 3B 3C 3I 3F 3L 3K
58 3H 3G 3B 3D 3I 3F 3L 3K
87 3H 3G 3B 3C 3J 3F 3L 3I
59 3H 3G 3B 3D 3J 3F 3L 3I
88 3H 3G 3B 3C 3J 3F 3I 3K
60 3H 3G 3B 3D 3J 3F 3I 3K
89 3E 3J 3B 3C 3I 3H 3L 3K
61 3E 3J 3B 3D 3I 3H 3L 3K
90 3E 3J 3B 3C 3I 3G 3L 3K
62 3E 3J 3B 3D 3I 3G 3L 3K
91 3E 3J 3B 3C 3H 3G 3L 3K
63 3E 3J 3B 3D 3H 3G 3L 3K
92 3E 3G 3B 3C 3I 3H 3L 3K
64 3E 3G 3B 3D 3I 3H 3L 3K
93 3E 3J 3B 3C 3H 3G 3L 3I
65 3E 3J 3B 3D 3H 3G 3L 3I
94 3E 3J 3B 3C 3H 3G 3I 3K
66 3E 3J 3B 3D 3H 3G 3I 3K
95 3E 3J 3B 3C 3I 3F 3L 3K
67 3E 3J 3B 3D 3I 3F 3L 3K
96 3E 3J 3B 3C 3H 3F 3L 3K
68 3E 3J 3B 3D 3H 3F 3L 3K
97 3E 3I 3B 3C 3H 3F 3L 3K
69 3E 3I 3B 3D 3H 3F 3L 3K
98 3E 3J 3B 3C 3H 3F 3L 3I
70 3E 3J 3B 3D 3H 3F 3L 3I
99 3E 3J 3B 3C 3H 3F 3I 3K
71 3E 3J 3B 3D 3H 3F 3I 3K
100 3E 3G 3B 3C 3J 3F 3L 3K
72 3E 3G 3B 3D 3J 3F 3L 3K
101 3E 3G 3B 3C 3I 3F 3L 3K
73 3E 3G 3B 3D 3I 3F 3L 3K
102 3E 3G 3B 3C 3J 3F 3L 3I
74 3E 3G 3B 3D 3J 3F 3L 3I
103 3E 3G 3B 3C 3J 3F 3I 3K
75 3E 3G 3B 3D 3J 3F 3I 3K
104 3E 3G 3B 3C 3H 3F 3L 3K
76 3E 3G 3B 3D 3H 3F 3L 3K
105 3H 3G 3B 3C 3J 3F 3L 3E
106 3H 3G 3B 3C 3J 3F 3E 3K
135 3E 3J 3B 3C 3H 3D 3I 3K
107 3E 3G 3B 3C 3H 3F 3L 3I
136 3E 3G 3B 3C 3J 3D 3L 3K
108 3E 3G 3B 3C 3H 3F 3I 3K
137 3E 3G 3B 3C 3I 3D 3L 3K
109 3H 3G 3B 3C 3J 3F 3E 3I
138 3E 3G 3B 3C 3J 3D 3L 3I
110 3H 3J 3B 3C 3I 3D 3L 3K
139 3E 3G 3B 3C 3J 3D 3I 3K
111 3I 3G 3B 3C 3J 3D 3L 3K
140 3E 3G 3B 3C 3H 3D 3L 3K
112 3H 3G 3B 3C 3J 3D 3L 3K
141 3H 3G 3B 3C 3J 3D 3L 3E
113 3H 3G 3B 3C 3I 3D 3L 3K
142 3H 3G 3B 3C 3J 3D 3E 3K
114 3H 3G 3B 3C 3J 3D 3L 3I
143 3E 3G 3B 3C 3H 3D 3L 3I
115 3H 3G 3B 3C 3J 3D 3I 3K
144 3E 3G 3B 3C 3H 3D 3I 3K
116 3C 3J 3B 3D 3I 3F 3L 3K
145 3H 3G 3B 3C 3J 3D 3E 3I
117 3C 3J 3B 3D 3H 3F 3L 3K
146 3C 3J 3B 3D 3E 3F 3L 3K
118 3C 3I 3B 3D 3H 3F 3L 3K
147 3C 3E 3B 3D 3I 3F 3L 3K
119 3C 3J 3B 3D 3H 3F 3L 3I
148 3C 3J 3B 3D 3E 3F 3L 3I
120 3C 3J 3B 3D 3H 3F 3I 3K
149 3C 3J 3B 3D 3E 3F 3I 3K
121 3C 3G 3B 3D 3J 3F 3L 3K
150 3C 3E 3B 3D 3H 3F 3L 3K
122 3C 3G 3B 3D 3I 3F 3L 3K
151 3C 3J 3B 3D 3H 3F 3L 3E
123 3C 3G 3B 3D 3J 3F 3L 3I
152 3C 3J 3B 3D 3H 3F 3E 3K
124 3C 3G 3B 3D 3J 3F 3I 3K
153 3C 3E 3B 3D 3H 3F 3L 3I
125 3C 3G 3B 3D 3H 3F 3L 3K
154 3C 3E 3B 3D 3H 3F 3I 3K
126 3C 3G 3B 3D 3H 3F 3L 3J
155 3C 3J 3B 3D 3H 3F 3E 3I
127 3H 3G 3B 3C 3J 3F 3D 3K
156 3C 3G 3B 3D 3E 3F 3L 3K
128 3C 3G 3B 3D 3H 3F 3L 3I
157 3C 3G 3B 3D 3J 3F 3L 3E
129 3C 3G 3B 3D 3H 3F 3I 3K
158 3C 3G 3B 3D 3J 3F 3E 3K
130 3H 3G 3B 3C 3J 3F 3D 3I
159 3C 3G 3B 3D 3E 3F 3L 3I
131 3E 3J 3B 3C 3I 3D 3L 3K
160 3C 3G 3B 3D 3E 3F 3I 3K
132 3E 3J 3B 3C 3H 3D 3L 3K
161 3C 3G 3B 3D 3J 3F 3E 3I
133 3E 3I 3B 3C 3H 3D 3L 3K
162 3C 3G 3B 3D 3H 3F 3L 3E
134 3E 3J 3B 3C 3H 3D 3L 3I
163 3C 3G 3B 3D 3H 3F 3E 3K
164 3H 3G 3B 3C 3J 3F 3D 3E
193 3E 3G 3I 3D 3A 3F 3L 3K
165 3C 3G 3B 3D 3H 3F 3E 3I
194 3E 3G 3J 3D 3A 3F 3L 3I
166 3H 3J 3I 3F 3A 3G 3L 3K
195 3E 3G 3J 3D 3A 3F 3I 3K
167 3E 3J 3I 3A 3H 3G 3L 3K
196 3H 3G 3E 3D 3A 3F 3L 3K
168 3E 3J 3I 3F 3A 3H 3L 3K
197 3H 3G 3J 3D 3A 3F 3L 3E
169 3E 3J 3I 3F 3A 3G 3L 3K
198 3H 3G 3J 3D 3A 3F 3E 3K
170 3E 3G 3J 3F 3A 3H 3L 3K
199 3H 3G 3E 3D 3A 3F 3L 3I
171 3E 3G 3I 3F 3A 3H 3L 3K
200 3H 3G 3E 3D 3A 3F 3I 3K
172 3E 3G 3J 3F 3A 3H 3L 3I
201 3H 3G 3J 3D 3A 3F 3E 3I
173 3E 3G 3J 3F 3A 3H 3I 3K
202 3H 3J 3I 3C 3A 3G 3L 3K
174 3H 3J 3I 3D 3A 3G 3L 3K
203 3H 3J 3I 3C 3A 3F 3L 3K
175 3H 3J 3I 3D 3A 3F 3L 3K
204 3I 3G 3J 3C 3A 3F 3L 3K
176 3I 3G 3J 3D 3A 3F 3L 3K
205 3H 3G 3J 3C 3A 3F 3L 3K
177 3H 3G 3J 3D 3A 3F 3L 3K
206 3H 3G 3I 3C 3A 3F 3L 3K
178 3H 3G 3I 3D 3A 3F 3L 3K
207 3H 3G 3J 3C 3A 3F 3L 3I
179 3H 3G 3J 3D 3A 3F 3L 3I
208 3H 3G 3J 3C 3A 3F 3I 3K
180 3H 3G 3J 3D 3A 3F 3I 3K
209 3E 3J 3I 3C 3A 3H 3L 3K
181 3E 3J 3I 3D 3A 3H 3L 3K
210 3E 3J 3I 3C 3A 3G 3L 3K
182 3E 3J 3I 3D 3A 3G 3L 3K
211 3E 3G 3J 3C 3A 3H 3L 3K
183 3E 3G 3J 3D 3A 3H 3L 3K
212 3E 3G 3I 3C 3A 3H 3L 3K
184 3E 3G 3I 3D 3A 3H 3L 3K
213 3E 3G 3J 3C 3A 3H 3L 3I
185 3E 3G 3J 3D 3A 3H 3L 3I
214 3E 3G 3J 3C 3A 3H 3I 3K
186 3E 3G 3J 3D 3A 3H 3I 3K
215 3E 3J 3I 3C 3A 3F 3L 3K
187 3E 3J 3I 3D 3A 3F 3L 3K
216 3H 3J 3E 3C 3A 3F 3L 3K
188 3H 3J 3E 3D 3A 3F 3L 3K
217 3H 3E 3I 3C 3A 3F 3L 3K
189 3H 3E 3I 3D 3A 3F 3L 3K
218 3H 3J 3E 3C 3A 3F 3L 3I
190 3H 3J 3E 3D 3A 3F 3L 3I
219 3H 3J 3E 3C 3A 3F 3I 3K
191 3H 3J 3E 3D 3A 3F 3I 3K
220 3E 3G 3J 3C 3A 3F 3L 3K
192 3E 3G 3J 3D 3A 3F 3L 3K
221 3E 3G 3I 3C 3A 3F 3L 3K
222 3E 3G 3J 3C 3A 3F 3L 3I
251 3E 3J 3I 3C 3A 3D 3L 3K
223 3E 3G 3J 3C 3A 3F 3I 3K
252 3H 3J 3E 3C 3A 3D 3L 3K
224 3H 3G 3E 3C 3A 3F 3L 3K
253 3H 3E 3I 3C 3A 3D 3L 3K
225 3H 3G 3J 3C 3A 3F 3L 3E
254 3H 3J 3E 3C 3A 3D 3L 3I
226 3H 3G 3J 3C 3A 3F 3E 3K
255 3H 3J 3E 3C 3A 3D 3I 3K
227 3H 3G 3E 3C 3A 3F 3L 3I
256 3E 3G 3J 3C 3A 3D 3L 3K
228 3H 3G 3E 3C 3A 3F 3I 3K
257 3E 3G 3I 3C 3A 3D 3L 3K
229 3H 3G 3J 3C 3A 3F 3E 3I
258 3E 3G 3J 3C 3A 3D 3L 3I
230 3H 3J 3I 3C 3A 3D 3L 3K
259 3E 3G 3J 3C 3A 3D 3I 3K
231 3I 3G 3J 3C 3A 3D 3L 3K
260 3H 3G 3E 3C 3A 3D 3L 3K
232 3H 3G 3J 3C 3A 3D 3L 3K
261 3H 3G 3J 3C 3A 3D 3L 3E
233 3H 3G 3I 3C 3A 3D 3L 3K
262 3H 3G 3J 3C 3A 3D 3E 3K
234 3H 3G 3J 3C 3A 3D 3L 3I
263 3H 3G 3E 3C 3A 3D 3L 3I
235 3H 3G 3J 3C 3A 3D 3I 3K
264 3H 3G 3E 3C 3A 3D 3I 3K
236 3C 3J 3I 3D 3A 3F 3L 3K
265 3H 3G 3J 3C 3A 3D 3E 3I
237 3H 3J 3F 3C 3A 3D 3L 3K
266 3C 3J 3E 3D 3A 3F 3L 3K
238 3H 3F 3I 3C 3A 3D 3L 3K
267 3C 3E 3I 3D 3A 3F 3L 3K
239 3H 3J 3F 3C 3A 3D 3L 3I
268 3C 3J 3E 3D 3A 3F 3L 3I
240 3H 3J 3F 3C 3A 3D 3I 3K
269 3C 3J 3E 3D 3A 3F 3I 3K
241 3C 3G 3J 3D 3A 3F 3L 3K
270 3H 3E 3F 3C 3A 3D 3L 3K
242 3C 3G 3I 3D 3A 3F 3L 3K
271 3H 3J 3F 3C 3A 3D 3L 3E
243 3C 3G 3J 3D 3A 3F 3L 3I
272 3H 3J 3E 3C 3A 3F 3D 3K
244 3C 3G 3J 3D 3A 3F 3I 3K
273 3H 3E 3F 3C 3A 3D 3L 3I
245 3H 3G 3F 3C 3A 3D 3L 3K
274 3H 3E 3F 3C 3A 3D 3I 3K
246 3C 3G 3J 3D 3A 3F 3L 3H
275 3H 3J 3E 3C 3A 3F 3D 3I
247 3H 3G 3J 3C 3A 3F 3D 3K
276 3C 3G 3E 3D 3A 3F 3L 3K
248 3H 3G 3F 3C 3A 3D 3L 3I
277 3C 3G 3J 3D 3A 3F 3L 3E
249 3H 3G 3F 3C 3A 3D 3I 3K
278 3C 3G 3J 3D 3A 3F 3E 3K
250 3H 3G 3J 3C 3A 3F 3D 3I
279 3C 3G 3E 3D 3A 3F 3L 3I
280 3C 3G 3E 3D 3A 3F 3I 3K
309 3H 3J 3B 3F 3A 3G 3L 3E
281 3C 3G 3J 3D 3A 3F 3E 3I
310 3H 3J 3B 3F 3A 3G 3E 3K
282 3H 3G 3F 3C 3A 3D 3L 3E
311 3E 3G 3B 3F 3A 3H 3L 3I
283 3H 3G 3E 3C 3A 3F 3D 3K
312 3E 3G 3B 3F 3A 3H 3I 3K
284 3H 3G 3J 3C 3A 3F 3D 3E
313 3H 3J 3B 3F 3A 3G 3E 3I
285 3H 3G 3E 3C 3A 3F 3D 3I
314 3I 3J 3B 3D 3A 3H 3L 3K
286 3H 3J 3B 3A 3I 3G 3L 3K
315 3I 3J 3B 3D 3A 3G 3L 3K
287 3H 3J 3B 3A 3I 3F 3L 3K
316 3H 3J 3B 3D 3A 3G 3L 3K
288 3I 3J 3B 3F 3A 3G 3L 3K
317 3I 3G 3B 3D 3A 3H 3L 3K
289 3H 3J 3B 3F 3A 3G 3L 3K
318 3H 3J 3B 3D 3A 3G 3L 3I
290 3H 3G 3B 3A 3I 3F 3L 3K
319 3H 3J 3B 3D 3A 3G 3I 3K
291 3H 3J 3B 3F 3A 3G 3L 3I
320 3I 3J 3B 3D 3A 3F 3L 3K
292 3H 3J 3B 3F 3A 3G 3I 3K
321 3H 3J 3B 3D 3A 3F 3L 3K
293 3E 3J 3B 3A 3I 3H 3L 3K
322 3H 3I 3B 3D 3A 3F 3L 3K
294 3E 3J 3B 3A 3I 3G 3L 3K
323 3H 3J 3B 3D 3A 3F 3L 3I
295 3E 3J 3B 3A 3H 3G 3L 3K
324 3H 3J 3B 3D 3A 3F 3I 3K
296 3E 3G 3B 3A 3I 3H 3L 3K
325 3F 3J 3B 3D 3A 3G 3L 3K
297 3E 3J 3B 3A 3H 3G 3L 3I
326 3I 3G 3B 3D 3A 3F 3L 3K
298 3E 3J 3B 3A 3H 3G 3I 3K
327 3F 3J 3B 3D 3A 3G 3L 3I
299 3E 3J 3B 3A 3I 3F 3L 3K
328 3F 3J 3B 3D 3A 3G 3I 3K
300 3E 3J 3B 3F 3A 3H 3L 3K
329 3H 3G 3B 3D 3A 3F 3L 3K
301 3E 3I 3B 3F 3A 3H 3L 3K
330 3H 3G 3B 3D 3A 3F 3L 3J
302 3E 3J 3B 3F 3A 3H 3L 3I
331 3H 3G 3B 3D 3A 3F 3J 3K
303 3E 3J 3B 3F 3A 3H 3I 3K
332 3H 3G 3B 3D 3A 3F 3L 3I
304 3E 3J 3B 3F 3A 3G 3L 3K
333 3H 3G 3B 3D 3A 3F 3I 3K
305 3E 3G 3B 3A 3I 3F 3L 3K
334 3H 3G 3B 3D 3A 3F 3I 3J
306 3E 3J 3B 3F 3A 3G 3L 3I
335 3E 3J 3B 3A 3I 3D 3L 3K
307 3E 3J 3B 3F 3A 3G 3I 3K
336 3E 3J 3B 3D 3A 3H 3L 3K
308 3E 3G 3B 3F 3A 3H 3L 3K
337 3E 3I 3B 3D 3A 3H 3L 3K
338 3E 3J 3B 3D 3A 3H 3L 3I
367 3H 3G 3B 3D 3A 3F 3E 3K
339 3E 3J 3B 3D 3A 3H 3I 3K
368 3H 3G 3B 3D 3A 3F 3E 3J
340 3E 3J 3B 3D 3A 3G 3L 3K
369 3H 3G 3B 3D 3A 3F 3E 3I
341 3E 3G 3B 3A 3I 3D 3L 3K
370 3I 3J 3B 3C 3A 3H 3L 3K
342 3E 3J 3B 3D 3A 3G 3L 3I
371 3I 3J 3B 3C 3A 3G 3L 3K
343 3E 3J 3B 3D 3A 3G 3I 3K
372 3H 3J 3B 3C 3A 3G 3L 3K
344 3E 3G 3B 3D 3A 3H 3L 3K
373 3I 3G 3B 3C 3A 3H 3L 3K
345 3H 3J 3B 3D 3A 3G 3L 3E
374 3H 3J 3B 3C 3A 3G 3L 3I
346 3H 3J 3B 3D 3A 3G 3E 3K
375 3H 3J 3B 3C 3A 3G 3I 3K
347 3E 3G 3B 3D 3A 3H 3L 3I
376 3I 3J 3B 3C 3A 3F 3L 3K
348 3E 3G 3B 3D 3A 3H 3I 3K
377 3H 3J 3B 3C 3A 3F 3L 3K
349 3H 3J 3B 3D 3A 3G 3E 3I
378 3H 3I 3B 3C 3A 3F 3L 3K
350 3E 3J 3B 3D 3A 3F 3L 3K
379 3H 3J 3B 3C 3A 3F 3L 3I
351 3E 3I 3B 3D 3A 3F 3L 3K
380 3H 3J 3B 3C 3A 3F 3I 3K
352 3E 3J 3B 3D 3A 3F 3L 3I
381 3C 3J 3B 3F 3A 3G 3L 3K
353 3E 3J 3B 3D 3A 3F 3I 3K
382 3I 3G 3B 3C 3A 3F 3L 3K
354 3H 3E 3B 3D 3A 3F 3L 3K
383 3C 3J 3B 3F 3A 3G 3L 3I
355 3H 3J 3B 3D 3A 3F 3L 3E
384 3C 3J 3B 3F 3A 3G 3I 3K
356 3H 3J 3B 3D 3A 3F 3E 3K
385 3H 3G 3B 3C 3A 3F 3L 3K
357 3H 3E 3B 3D 3A 3F 3L 3I
386 3H 3G 3B 3C 3A 3F 3L 3J
358 3H 3E 3B 3D 3A 3F 3I 3K
387 3H 3G 3B 3C 3A 3F 3J 3K
359 3H 3J 3B 3D 3A 3F 3E 3I
388 3H 3G 3B 3C 3A 3F 3L 3I
360 3E 3G 3B 3D 3A 3F 3L 3K
389 3H 3G 3B 3C 3A 3F 3I 3K
361 3E 3G 3B 3D 3A 3F 3L 3J
390 3H 3G 3B 3C 3A 3F 3I 3J
362 3E 3G 3B 3D 3A 3F 3J 3K
391 3E 3J 3B 3A 3I 3C 3L 3K
363 3E 3G 3B 3D 3A 3F 3L 3I
392 3E 3J 3B 3C 3A 3H 3L 3K
364 3E 3G 3B 3D 3A 3F 3I 3K
393 3E 3I 3B 3C 3A 3H 3L 3K
365 3E 3G 3B 3D 3A 3F 3I 3J
394 3E 3J 3B 3C 3A 3H 3L 3I
366 3H 3G 3B 3D 3A 3F 3L 3E
395 3E 3J 3B 3C 3A 3H 3I 3K
396 3E 3J 3B 3C 3A 3G 3L 3K
425 3H 3G 3B 3C 3A 3F 3E 3I
397 3E 3G 3B 3A 3I 3C 3L 3K
426 3I 3J 3B 3C 3A 3D 3L 3K
398 3E 3J 3B 3C 3A 3G 3L 3I
427 3H 3J 3B 3C 3A 3D 3L 3K
399 3E 3J 3B 3C 3A 3G 3I 3K
428 3H 3I 3B 3C 3A 3D 3L 3K
400 3E 3G 3B 3C 3A 3H 3L 3K
429 3H 3J 3B 3C 3A 3D 3L 3I
401 3H 3J 3B 3C 3A 3G 3L 3E
430 3H 3J 3B 3C 3A 3D 3I 3K
402 3H 3J 3B 3C 3A 3G 3E 3K
431 3C 3J 3B 3D 3A 3G 3L 3K
403 3E 3G 3B 3C 3A 3H 3L 3I
432 3I 3G 3B 3C 3A 3D 3L 3K
404 3E 3G 3B 3C 3A 3H 3I 3K
433 3C 3J 3B 3D 3A 3G 3L 3I
405 3H 3J 3B 3C 3A 3G 3E 3I
434 3C 3J 3B 3D 3A 3G 3I 3K
406 3E 3J 3B 3C 3A 3F 3L 3K
435 3H 3G 3B 3C 3A 3D 3L 3K
407 3E 3I 3B 3C 3A 3F 3L 3K
436 3H 3G 3B 3C 3A 3D 3L 3J
408 3E 3J 3B 3C 3A 3F 3L 3I
437 3H 3G 3B 3C 3A 3D 3J 3K
409 3E 3J 3B 3C 3A 3F 3I 3K
438 3H 3G 3B 3C 3A 3D 3L 3I
410 3H 3E 3B 3C 3A 3F 3L 3K
439 3H 3G 3B 3C 3A 3D 3I 3K
411 3H 3J 3B 3C 3A 3F 3L 3E
440 3H 3G 3B 3C 3A 3D 3I 3J
412 3H 3J 3B 3C 3A 3F 3E 3K
441 3C 3J 3B 3D 3A 3F 3L 3K
413 3H 3E 3B 3C 3A 3F 3L 3I
442 3C 3I 3B 3D 3A 3F 3L 3K
414 3H 3E 3B 3C 3A 3F 3I 3K
443 3C 3J 3B 3D 3A 3F 3L 3I
415 3H 3J 3B 3C 3A 3F 3E 3I
444 3C 3J 3B 3D 3A 3F 3I 3K
416 3E 3G 3B 3C 3A 3F 3L 3K
445 3H 3F 3B 3C 3A 3D 3L 3K
417 3E 3G 3B 3C 3A 3F 3L 3J
446 3C 3J 3B 3D 3A 3F 3L 3H
418 3E 3G 3B 3C 3A 3F 3J 3K
447 3H 3J 3B 3C 3A 3F 3D 3K
419 3E 3G 3B 3C 3A 3F 3L 3I
448 3H 3F 3B 3C 3A 3D 3L 3I
420 3E 3G 3B 3C 3A 3F 3I 3K
449 3H 3F 3B 3C 3A 3D 3I 3K
421 3E 3G 3B 3C 3A 3F 3I 3J
450 3H 3J 3B 3C 3A 3F 3D 3I
422 3H 3G 3B 3C 3A 3F 3L 3E
451 3C 3G 3B 3D 3A 3F 3L 3K
423 3H 3G 3B 3C 3A 3F 3E 3K
452 3C 3G 3B 3D 3A 3F 3L 3J
424 3H 3G 3B 3C 3A 3F 3E 3J
453 3C 3G 3B 3D 3A 3F 3J 3K
454 3C 3G 3B 3D 3A 3F 3L 3I
483 3C 3J 3B 3D 3A 3F 3E 3K
455 3C 3G 3B 3D 3A 3F 3I 3K
484 3C 3E 3B 3D 3A 3F 3L 3I
456 3C 3G 3B 3D 3A 3F 3I 3J
485 3C 3E 3B 3D 3A 3F 3I 3K
457 3C 3G 3B 3D 3A 3F 3L 3H
486 3C 3J 3B 3D 3A 3F 3E 3I
458 3H 3G 3B 3C 3A 3F 3D 3K
487 3H 3F 3B 3C 3A 3D 3L 3E
459 3H 3G 3B 3C 3A 3F 3D 3J
488 3H 3E 3B 3C 3A 3F 3D 3K
460 3H 3G 3B 3C 3A 3F 3D 3I
489 3H 3J 3B 3C 3A 3F 3D 3E
461 3E 3J 3B 3C 3A 3D 3L 3K
490 3H 3E 3B 3C 3A 3F 3D 3I
462 3E 3I 3B 3C 3A 3D 3L 3K
491 3C 3G 3B 3D 3A 3F 3L 3E
463 3E 3J 3B 3C 3A 3D 3L 3I
492 3C 3G 3B 3D 3A 3F 3E 3K
464 3E 3J 3B 3C 3A 3D 3I 3K
493 3C 3G 3B 3D 3A 3F 3E 3J
465 3H 3E 3B 3C 3A 3D 3L 3K
494 3C 3G 3B 3D 3A 3F 3E 3I
466 3H 3J 3B 3C 3A 3D 3L 3E
495 3H 3G 3B 3C 3A 3F 3D 3E
467 3H 3J 3B 3C 3A 3D 3E 3K
468 3H 3E 3B 3C 3A 3D 3L 3I
469 3H 3E 3B 3C 3A 3D 3I 3K
470 3H 3J 3B 3C 3A 3D 3E 3I
471 3E 3G 3B 3C 3A 3D 3L 3K
472 3E 3G 3B 3C 3A 3D 3L 3J
473 3E 3G 3B 3C 3A 3D 3J 3K
474 3E 3G 3B 3C 3A 3D 3L 3I
475 3E 3G 3B 3C 3A 3D 3I 3K
476 3E 3G 3B 3C 3A 3D 3I 3J
477 3H 3G 3B 3C 3A 3D 3L 3E
478 3H 3G 3B 3C 3A 3D 3E 3K
479 3H 3G 3B 3C 3A 3D 3E 3J
480 3H 3G 3B 3C 3A 3D 3E 3I
481 3C 3E 3B 3D 3A 3F 3L 3K
482 3C 3J 3B 3D 3A 3F 3L 3E
        """

        return first_place_teams, raw_data

    def _load_third_place_combinations(self):
        """Parse the 495 third-place team combinations."""
        first_place_teams, raw_data = self._get_third_place_combinations_data()

        combinations = {}

        # Process each line
        for line in raw_data.strip().split('\n'):
            if not line.strip():
                continue

            parts = line.strip().split()
            if len(parts) != 9:  # Option + 8 third-place teams
                continue

            option_number = parts[0]
            third_place_teams = parts[1:]

            # Convert to bit vector for efficient lookup
            bit_vector = self._teams_to_bit_vector(third_place_teams)

            # Create matchups dictionary
            matchups = {}
            for i, first_place in enumerate(first_place_teams):
                matchups[first_place] = third_place_teams[i]

            # Store with bit vector as key (as string since JSON keys must be strings)
            combinations[str(bit_vector)] = {
                'option': option_number,
                'teams': third_place_teams,  # Store for reference
                'matchups': matchups
            }

        return combinations

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE(
            'Starting 2026 World Cup bracket seeding...'))

        # Get or create a system user for bracket creation
        user, created = User.objects.get_or_create(
            username='system',
            defaults={
                'email': 'system@brackets.win',
                'is_staff': True,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS('Created system user'))

        # Check if bracket already exists
        if Bracket.objects.filter(name='2026 FIFA World Cup').exists():
            self.stdout.write(self.style.WARNING(
                '2026 FIFA World Cup bracket already exists. Skipping.'))
            return

        # Load third-place combinations from file
        third_place_combinations = self._load_third_place_combinations()
        self.stdout.write(self.style.SUCCESS(
            f'Loaded {len(third_place_combinations)} third-place combinations'))

        # Create the bracket with metadata
        bracket = Bracket.objects.create(
            name='2026 FIFA World Cup',
            description='The 2026 FIFA World Cup with 48 teams, 12 groups, and knockout rounds',
            created_by=user,
            metadata={
                'third_place_combinations': third_place_combinations,
                'tournament_type': 'world_cup_2026',
                'lookup_info': {
                    'type': 'bit_vector',
                    'description': 'Each group A-L is a bit position (A=0, B=1, ..., L=11)',
                    'example': 'teams_to_bits(["3B", "3C"]) = 0b110 = 6'
                }
            }
        )
        self.stdout.write(self.style.SUCCESS(
            f'Created bracket: {bracket.name}'))

        from brackets.utils.group_knockout_mapping import set_custom_group_knockout_mapping

        # World Cup 2026 Round of 32 mapping (from FIFA regulations)
        # Note: Codes starting with '1' or '2' = group position (e.g., '1A' = first place Group A)
        #       Codes starting with '3RD_' = third-place team from 495 combinations lookup
        #       The combinations determine which specific 3rd place team based on
        #       which 8 of the 12 third-place teams advance
        r32_mapping = [
            (1, 'A2', 'B2'),             # M73: Runner-up A vs Runner-up B
            # M74: Winner E vs 3rd place opponent of E
            (2, 'E1', '3E'),
            (3, 'F1', 'C2'),             # M75: Winner F vs Runner-up C
            (4, 'C1', 'F2'),             # M76: Winner C vs Runner-up F
            # M77: Winner I vs 3rd place opponent of I
            (5, 'I1', '3I'),
            (6, 'E2', 'I2'),             # M78: Runner-up E vs Runner-up I
            # M79: Winner A vs 3rd place opponent of A
            (7, 'A1', '3A'),
            # M80: Winner L vs 3rd place opponent of L
            (8, 'L1', '3L'),
            # M81: Winner D vs 3rd place opponent of D
            (9, 'D1', '3D'),
            # M82: Winner G vs 3rd place opponent of G
            (10, 'G1', '3G'),
            (11, 'K2', 'L2'),            # M83: Runner-up K vs Runner-up L
            (12, 'H1', 'J2'),            # M84: Winner H vs Runner-up J
            # M85: Winner B vs 3rd place opponent of B
            (13, 'B1', '3B'),
            (14, 'J1', 'H2'),            # M86: Winner J vs Runner-up H
            # M87: Winner K vs 3rd place opponent of K
            (15, 'K1', '3K'),
            (16, 'D2', 'G2'),            # M88: Runner-up D vs Runner-up G
        ]
        self.stdout.write(self.style.SUCCESS(
            f'Loaded {len(r32_mapping)} Round of 32 matchups'))

        # Create Group Stage
        group_stage = GroupStage.objects.create(
            bracket=bracket,
            name='Group Stage',
            order=1,
            stage_type='GROUP',
            number_of_contestants=48,
            contestants_advancing=32,
            is_random_draw=False,
            number_of_groups=12,
            matches_per_contestant=3,
            contestants_qualifying_per_group=2,
            remaining_spots_strategy='HighestPlaceWithinGroup',
            points_per_win=3,
            points_per_tie=1,
            points_per_loss=0,
            ties_allowed=True,
        )
        self.stdout.write(self.style.SUCCESS(
            f'Created stage: {group_stage.name}'))

        # Create Knockout Stages
        knockout_stages = [
            {
                'name': 'Round of 32',
                'order': 2,
                'number_of_contestants': 32,
                'contestants_advancing': 16,
                'is_final': False,
                'custom_mapping': r32_mapping,  # Use World Cup R32 mapping
            },
            {
                'name': 'Round of 16',
                'order': 3,
                'number_of_contestants': 16,
                'contestants_advancing': 8,
                'is_final': False,
            },
            {
                'name': 'Quarter Final',
                'order': 4,
                'number_of_contestants': 8,
                'contestants_advancing': 4,
                'is_final': False,
            },
            {
                'name': 'Semi Final',
                'order': 5,
                'number_of_contestants': 4,
                'contestants_advancing': 2,
                'is_final': False,
            },
            {
                'name': 'Final',
                'order': 6,
                'number_of_contestants': 2,
                'contestants_advancing': 1,
                'is_final': True,
            },
        ]

        for stage_data in knockout_stages:
            knockout_stage = KnockoutStage.objects.create(
                bracket=bracket,
                name=stage_data['name'],
                order=stage_data['order'],
                stage_type='KNOCKOUT',
                number_of_contestants=stage_data['number_of_contestants'],
                contestants_advancing=stage_data['contestants_advancing'],
                is_random_draw=False,
                number_of_legs=1,
                has_extra_time=True,
                has_penalty_shootout=True,
                is_final=stage_data['is_final'],
            )

            # Set custom mapping for Round of 32
            if 'custom_mapping' in stage_data:
                set_custom_group_knockout_mapping(
                    knockout_stage, stage_data['custom_mapping'])
                self.stdout.write(self.style.NOTICE(
                    f'  → Applied custom group-to-knockout mapping'))

            self.stdout.write(self.style.SUCCESS(
                f'Created stage: {knockout_stage.name}'))

        self.stdout.write(self.style.SUCCESS(
            '\n✓ 2026 FIFA World Cup bracket seeded successfully!'))
        self.stdout.write(self.style.NOTICE(
            f'Total stages created: {bracket.stages.count()}'))
