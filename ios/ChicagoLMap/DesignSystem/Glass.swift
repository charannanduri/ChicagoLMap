//
//  Glass.swift
//  ChicagoLMap
//
//  The single Liquid Glass abstraction used by the whole app.
//  On iOS 26+ this uses the real `glassEffect` API; on iOS 17–25 it renders a
//  beautiful `.ultraThinMaterial` fallback (fill + hairline stroke + soft shadow).
//

import SwiftUI

// MARK: - LiquidGlassModifier

struct LiquidGlassModifier<S: Shape>: ViewModifier {
    let shape: S
    let interactive: Bool
    let tint: Color?

    @ViewBuilder
    func body(content: Content) -> some View {
        if #available(iOS 26.0, *) {
            content.glassEffect(glassStyle, in: shape)
        } else {
            content
                .background {
                    ZStack {
                        shape.fill(.ultraThinMaterial)
                        if let tint {
                            shape.fill(tint.opacity(0.18))
                        }
                        shape.stroke(Color.white.opacity(0.12), lineWidth: 0.5)
                    }
                    .compositingGroup()
                    .shadow(color: Color.black.opacity(0.25), radius: 10, x: 0, y: 4)
                }
        }
    }

    @available(iOS 26.0, *)
    private var glassStyle: Glass {
        var glass: Glass = .regular
        if let tint {
            glass = glass.tint(tint)
        }
        if interactive {
            glass = glass.interactive()
        }
        return glass
    }
}

// MARK: - View conveniences

extension View {
    /// Applies Liquid Glass in the given shape.
    /// iOS 26: real `.glassEffect(...)`; earlier: `.ultraThinMaterial` fill
    /// with a subtle stroke and soft shadow.
    func liquidGlass(in shape: some Shape, interactive: Bool = false, tint: Color? = nil) -> some View {
        modifier(LiquidGlassModifier(shape: shape, interactive: interactive, tint: tint))
    }

    /// Capsule-shaped Liquid Glass — the most common shape in the app.
    func liquidGlassCapsule(interactive: Bool = false, tint: Color? = nil) -> some View {
        liquidGlass(in: Capsule(), interactive: interactive, tint: tint)
    }
}

// MARK: - GlassGroup

/// Groups glass shapes so iOS 26 can morph/blend them together
/// (`GlassEffectContainer`); on earlier OS versions the content is passed
/// through unchanged.
struct GlassGroup<Content: View>: View {
    private let spacing: CGFloat
    private let content: Content

    init(spacing: CGFloat = 12, @ViewBuilder content: () -> Content) {
        self.spacing = spacing
        self.content = content()
    }

    var body: some View {
        if #available(iOS 26.0, *) {
            GlassEffectContainer(spacing: spacing) {
                content
            }
        } else {
            content
        }
    }
}
