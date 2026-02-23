"""Утилиты для загрузки файлов: лимиты размера, валидация."""
from fastapi import HTTPException, UploadFile


async def read_with_limit(file: UploadFile, max_bytes: int) -> bytes:
    """
    Прочитать файл с ограничением размера.
    """
    if max_bytes <= 0:
        return await file.read()
    # Читаем по чанкам, не превышая лимит
    chunks = []
    total = 0
    chunk_size = min(1024 * 1024, max_bytes)  # 1 MB за раз
    while total < max_bytes:
        to_read = min(chunk_size, max_bytes - total)
        chunk = await file.read(to_read)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if len(chunk) < to_read:
            break
    if total > max_bytes:
        raise HTTPException(
            413,
            f"Файл слишком большой (>{max_bytes:,} байт). Максимум: {max_bytes:,}",
        )
    return b"".join(chunks)
