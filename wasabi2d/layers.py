from typing import Tuple, Optional

from .sprites import SpriteArray, Sprite
from .atlas import Atlas
from .primitives.circles import Circle, line_vao, shape_vao
from .primitives.polygons import Polygon, Rect, PolyLine
from .primitives.text import Label, FontAtlas, text_vao


class ShaderManager:
    def __init__(self, ctx):
        self.ctx = ctx
        self.programs = {}

    def get(self, vertex_shader, fragment_shader, geometry_shader=None):
        """Get a compiled program."""
        k = vertex_shader, fragment_shader
        try:
            return self.programs[k]
        except KeyError:
            prog = self.programs[k] = self.ctx.program(
                vertex_shader=vertex_shader,
                fragment_shader=fragment_shader,
                geometry_shader=geometry_shader,
            )
            return prog

    def set_proj(self, proj):
        """Set the projection matrix."""
        for prog in self.programs.values():
            prog['proj'].write(proj.tobytes())


class FontManager:
    def __init__(self, ctx):
        self.ctx = ctx
        self.font_atlases = {}

    def get(self, font_name):
        try:
            return self.font_atlases[font_name]
        except KeyError:
            fa = self.font_atlases[font_name] = FontAtlas(self.ctx, font_name)
            return fa

    def update(self):
        """Send any dirty textures to the GL."""
        for f in self.font_atlases.values():
            f._update()


class Layer:
    def __init__(self, ctx, group):
        self.ctx = ctx
        self.group = group
        self.arrays = {}
        self.visible = True
        self.objects = set()
        self._dirty = set()

    def clear(self):
        """Remove everything from the layer."""
        # We don't need to call .delete() on anything, faster to throw away
        # absolutely everything including VAOs.
        self.arrays.clear()
        self.objects.clear()
        self._dirty.clear()

    def render(self, t, dt):
        """Render the layer."""
        if not self.visible:
            return

        for o in self._dirty:
            o._update()
        self._dirty.clear()
        for a in self.arrays.values():
            a.render()

    def add_sprite(self, image, pos=(0, 0), angle=0, anchor=None):
        spr = Sprite(
            layer=self,
            image=image,
            anchor=anchor
        )
        spr.pos = pos
        spr.angle = angle
        self.objects.add(spr)
        return spr

    def _migrate_sprite(self, spr, tex):
        """Move sprite spr into the correct vertex array."""
        k = ('sprite', tex.glo)
        array = self.arrays.get(k)
        if not array:
            prog = self.group.shadermgr.get(**SpriteArray.PROGRAM)
            array = SpriteArray(self.ctx, prog, tex, [spr])
            self.arrays[k] = array
        else:
            array.add(spr)

    def _lines_vao(self):
        """Get a VAO for objects made of line strips."""
        k = 'lines'
        vao = self.arrays.get(k)
        if not vao:
            vao = self.arrays[k] = line_vao(self.ctx, self.group.shadermgr)
        return vao

    def _fill_vao(self):
        """Get a VAO for objects made of line strips."""
        k = 'shapes'
        vao = self.arrays.get(k)
        if not vao:
            vao = self.arrays[k] = shape_vao(self.ctx, self.group.shadermgr)
        return vao

    def _text_vao(self, font):
        """Get a VAO for objects made of font glyphs."""
        k = 'text', font
        vao = self.arrays.get(k)
        if not vao:
            vao = self.arrays[k] = text_vao(self.ctx, self.group.shadermgr)
        return vao

    def add_circle(self,
                   *,
                   radius: float,
                   pos: Tuple[float, float] = (0, 0),
                   color: Tuple[float, float, float, float] = (1, 1, 1, 1),
                   fill: bool = True,
                   stroke_width: float = 1.0,
                   ) -> Circle:
        c = Circle(
            layer=self,
            radius=radius,
            pos=pos,
            color=color,
            stroke_width=stroke_width,
        )
        if fill:
            c._migrate_fill(self._fill_vao())
        else:
            c._migrate_stroke(self._lines_vao())
        self.objects.add(c)
        return c

    def add_star(
            self,
            *,
            points: int,
            inner_radius: float = 1.0,
            outer_radius: float = None,
            pos: Tuple[float, float] = (0, 0),
            fill: bool = True,
            color: Tuple[float, float, float, float] = (1, 1, 1, 1),
            stroke_width: float = 1.0,
    ) -> Circle:
        assert points >= 3, "Stars must have at least 3 points."

        if outer_radius is None:
            outer_radius = inner_radius * 2

        c = Circle(
            layer=self,
            segments=2 * points + 1,
            radius=1.0,
            pos=pos,
            color=color,
            stroke_width=stroke_width,
        )
        if fill:
            c._migrate_fill(self._fill_vao())
        else:
            c._migrate_stroke(self._lines_vao())
        self.objects.add(c)
        c.orig_verts[::2, :2] *= outer_radius
        c.orig_verts[1::2, :2] *= inner_radius
        return c

    def add_polygon(self,
                    vertices,
                    *,
                    pos: Tuple[float, float] = (0, 0),
                    color: Tuple[float, float, float, float] = (1, 1, 1, 1),
                    fill: bool = True,
                    stroke_width: float = 1.0,
                    ) -> Polygon:
        c = Polygon(
            layer=self,
            vertices=vertices,
            pos=pos,
            color=color,
            stroke_width=stroke_width,
        )
        self.objects.add(c)
        if fill:
            c._migrate_fill(self._fill_vao())
        else:
            c._migrate_stroke(self._lines_vao())
        return c

    def add_line(self,
                 vertices,
                 *,
                 pos: Tuple[float, float] = (0, 0),
                 color: Tuple[float, float, float, float] = (1, 1, 1, 1),
                 stroke_width: float = 1.0,
                 ) -> PolyLine:
        """Add a line strip.

        To create a single line segment of two points, pass two vertices!

        """
        c = PolyLine(
            layer=self,
            vertices=vertices,
            pos=pos,
            color=color,
            stroke_width=stroke_width,
        )
        self.objects.add(c)
        c._migrate_stroke(self._lines_vao())
        return c

    def add_rect(
            self,
            width: float,
            height: float,
            *,
            pos: Tuple[float, float] = (0, 0),
            color: Tuple[float, float, float, float] = (1, 1, 1, 1),
            fill: bool = True) -> Rect:

        c = Rect(
            layer=self,
            width=width,
            height=height,
            pos=pos,
            color=color
        )
        self.objects.add(c)
        if fill:
            c._migrate_fill(self._fill_vao())
        else:
            c._migrate_stroke(self._lines_vao())
        return c

    def add_label(self,
                  text: str,
                  *,
                  font: Optional[str] = None,
                  align: str = 'left',
                  fontsize: int = 20,
                  pos: Tuple[float, float] = (0, 0),
                  color: Tuple[float, float, float, float] = (1, 1, 1, 1),
                  ) -> Rect:

        fa = self.group.fontmgr.get(font)
        c = Label(
            text,
            fa,
            self,
            align=align,
            fontsize=fontsize,
            pos=pos,
            color=color
        )
        self.objects.add(c)
        c._migrate(self._text_vao(font))
        return c


class LayerGroup(dict):
    def __new__(cls, ctx):
        return dict.__new__(cls)

    def __init__(self, ctx):
        self.ctx = ctx
        self.shadermgr = ShaderManager(self.ctx)
        self.fontmgr = FontManager(self.ctx)
        self.atlas = Atlas(ctx)

    def __missing__(self, k):
        if not isinstance(k, (float, int)):
            raise TypeError("Layer indices must be numbers")
        layer = self[k] = Layer(self.ctx, self)
        return layer

    def render(self, proj, t, dt):
        self.atlas._update()
        self.fontmgr.update()
        self.shadermgr.set_proj(proj)
        for k in sorted(self):
            self[k].render(t, dt)
