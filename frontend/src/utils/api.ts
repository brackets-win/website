const apiHost = import.meta.env.DEV
    ? 'http://localhost:8000'
    : 'https://brackets-win.fly.dev';

let csrfToken: Promise<string>;
csrfToken = getCSRF();

export async function makeRequest<T>(
    method: 'GET' | 'POST',
    path: string,
    body?: unknown
): Promise<T> {
    const response = await fetch(`${apiHost}/brackets/${path}`, {
        body: body ? JSON.stringify(body) : undefined,
        method,
        credentials: 'include',
        headers: {
            'X-CsrfToken': await csrfToken,
        }
    });
    return await response.json();
}

export async function getCSRF(): Promise<string> {
    const data = await makeRequest<{ data: string }>('GET', 'csrf');
    return data.data
}

export async function testAPI(value1: number, value2: number): Promise<number> {
    const data = await makeRequest<{ data: number }>('POST', 'test', {
        num1: value1,
        num2: value2,
    });
    return data.data
}
